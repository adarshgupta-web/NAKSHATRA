/*
 * NAKSHATRA drone logger - STM32F401 "Blackpill" (STM32duino core)
 *
 * Logs, to one SD card:
 *   gnssNNN.ubx raw bytes from the dual-band GNSS receiver (UBX, incl. RXM-RAWX/SFRBX)
 *   evtNNN.csv  P,<n>,<micros>               PPS rising edge
 *               T,<micros>,<week>,<tow_ms>   UBX NAV-TIMEGPS received
 *               C,<n>,<micros>               camera shutter / flash-sync edge
 *
 * Offline, ppk-processing/align_events.py maps local micros -> GPST.
 * STATUS: reference firmware, NOT yet compiled or run on hardware in this repo.
 * Configure the receiver (u-center or UBX-CFG) for: RAWX + SFRBX + NAV-TIMEGPS at 1 Hz,
 * 460800 baud, PPS enabled. Verify the NAV-TIMEGPS/PPS ordering assumption on your module.
 */
#include <SPI.h>
#include <SdFat.h>

// pins (see hardware/stm32-logger/README.md)
const uint8_t PIN_SD_CS = PA4;
const uint8_t PIN_PPS   = PB0;   // GNSS PPS, 3.3 V
const uint8_t PIN_CAM   = PB1;   // camera flash-sync / hot-shoe via optocoupler
const uint8_t PIN_LED   = PC13;  // on-board LED (active low)
HardwareSerial GNSS(PA10, PA9);  // RX, TX  (USART1)

SdFat sd;
FsFile gnssFile, evtFile;

volatile uint32_t ppsT[16], camT[16];
volatile uint8_t ppsHead = 0, ppsTail = 0, camHead = 0, camTail = 0;
volatile uint32_t ppsCount = 0, camCount = 0;

void ppsISR() { ppsT[ppsHead & 15] = micros(); ppsHead++; }
void camISR() { camT[camHead & 15] = micros(); camHead++; }

// --- minimal UBX frame parser: only NAV-TIMEGPS (0x01 0x20) is decoded ---
struct Ubx { uint8_t st = 0, cls, id, ck_a, ck_b; uint16_t len, n; uint8_t buf[32]; } u;

// tUs = micros() when the chunk was read; used only to order T after its PPS edge
static void ubxByte(uint8_t b, uint32_t tUs) {
  switch (u.st) {
    case 0: if (b == 0xB5) u.st = 1; break;
    case 1: u.st = (b == 0x62) ? 2 : 0; break;
    case 2: u.cls = b; u.ck_a = b; u.ck_b = b; u.st = 3; break;
    case 3: u.id = b; u.ck_a += b; u.ck_b += u.ck_a; u.st = 4; break;
    case 4: u.len = b; u.ck_a += b; u.ck_b += u.ck_a; u.st = 5; break;
    case 5: u.len |= (uint16_t)b << 8; u.ck_a += b; u.ck_b += u.ck_a; u.n = 0;
            u.st = (u.len == 0) ? 7 : (u.len > sizeof(u.buf) ? 0 : 6); break;
    case 6: u.buf[u.n++] = b; u.ck_a += b; u.ck_b += u.ck_a; if (u.n == u.len) u.st = 7; break;
    case 7: u.st = (b == u.ck_a) ? 8 : 0; break;
    case 8:
      if (b == u.ck_b && u.cls == 0x01 && u.id == 0x20 && u.len == 16) {
        uint32_t itow; int16_t week;
        memcpy(&itow, &u.buf[0], 4); memcpy(&week, &u.buf[8], 2);
        evtFile.printf("T,%lu,%d,%lu\n", (unsigned long)tUs, week, (unsigned long)itow);
      }
      u.st = 0; break;
  }
}

void setup() {
  pinMode(PIN_LED, OUTPUT); digitalWrite(PIN_LED, HIGH);
  pinMode(PIN_PPS, INPUT); pinMode(PIN_CAM, INPUT_PULLUP);
  GNSS.begin(460800);
  if (!sd.begin(PIN_SD_CS, SD_SCK_MHZ(25))) { while (1) { digitalToggle(PIN_LED); delay(100); } }  // fast blink = SD fail
  char ename[16], gname[16];
  int run = 1;
  for (; run < 1000; run++) { snprintf(ename, sizeof ename, "evt%03d.csv", run); if (!sd.exists(ename)) break; }
  snprintf(gname, sizeof gname, "gnss%03d.ubx", run);   // same run number for both files
  evtFile.open(ename, O_WRONLY | O_CREAT);
  gnssFile.open(gname, O_WRONLY | O_CREAT);
  attachInterrupt(PIN_PPS, ppsISR, RISING);
  attachInterrupt(PIN_CAM, camISR, FALLING);   // most flash-sync lines pull low at exposure
}

void loop() {
  static uint8_t buf[512]; static uint32_t lastSync = 0;
  int n = GNSS.available();
  if (n > 0) {
    n = GNSS.readBytes(buf, min(n, (int)sizeof buf));
    uint32_t t = micros();
    gnssFile.write(buf, n);
    for (int i = 0; i < n; i++) ubxByte(buf[i], t);
  }
  while (ppsTail != ppsHead) { evtFile.printf("P,%lu,%lu\n", (unsigned long)++ppsCount, (unsigned long)ppsT[ppsTail++ & 15]); }
  while (camTail != camHead) { evtFile.printf("C,%lu,%lu\n", (unsigned long)++camCount, (unsigned long)camT[camTail++ & 15]); }
  if (millis() - lastSync > 2000) {            // flush every 2 s: bounds data loss on power cut
    gnssFile.sync(); evtFile.sync(); lastSync = millis(); digitalToggle(PIN_LED);
  }
}
