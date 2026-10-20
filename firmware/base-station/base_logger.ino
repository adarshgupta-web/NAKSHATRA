/*
 * NAKSHATRA base-station logger - STM32F401 "Blackpill" (STM32duino core)
 * Streams raw GNSS bytes (UBX RXM-RAWX/SFRBX) from the pillar-mounted receiver to SD.
 * Leave it running >= 2 h (longer is better for the CORS baseline); LED slow-blinks while logging.
 * STATUS: reference firmware, NOT yet compiled or run on hardware in this repo.
 */
#include <SPI.h>
#include <SdFat.h>

const uint8_t PIN_SD_CS = PA4, PIN_LED = PC13;
HardwareSerial GNSS(PA10, PA9);   // RX, TX (USART1)
SdFat sd;
FsFile f;

void setup() {
  pinMode(PIN_LED, OUTPUT);
  GNSS.begin(460800);
  if (!sd.begin(PIN_SD_CS, SD_SCK_MHZ(25))) { while (1) { digitalToggle(PIN_LED); delay(100); } }
  char name[16];
  for (int i = 1; i < 1000; i++) { snprintf(name, sizeof name, "base%03d.ubx", i); if (!sd.exists(name)) break; }
  f.open(name, O_WRONLY | O_CREAT);
}

void loop() {
  static uint8_t buf[512]; static uint32_t last = 0;
  int n = GNSS.available();
  if (n > 0) f.write(buf, GNSS.readBytes(buf, min(n, (int)sizeof buf)));
  if (millis() - last > 2000) { f.sync(); digitalToggle(PIN_LED); last = millis(); }
}
