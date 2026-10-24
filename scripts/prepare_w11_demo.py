"""Prepare the installed Espressif CameraWebServer for the documented Meshnology W11.
Does not flash, mark a physical board verified, or alter the hosted uploader.
"""
import argparse
from pathlib import Path
import re
import shutil

SOURCE = 'https://wiki.meshnology.com/W11/W11_ESP32S3_Mini_Module/'
PINS = {'PWDN':-1,'RESET':-1,'XCLK':10,'SIOD':40,'SIOC':39,
        'Y2':15,'Y3':17,'Y4':18,'Y5':16,'Y6':14,'Y7':12,'Y8':11,'Y9':48,
        'VSYNC':38,'HREF':47,'PCLK':13}


def prepare(core, output):
    source = core/'libraries/ESP32/examples/Camera/CameraWebServer'
    pin_text = (source/'camera_pins.h').read_text()
    block = pin_text.split('#elif defined(CAMERA_MODEL_XIAO_ESP32S3)',1)[1].split('#elif',1)[0]
    for name, expected in PINS.items():
        actual = re.search(rf'#define\s+{name}_GPIO_NUM\s+(-?\d+)',block)
        if actual is None or int(actual[1]) != expected:
            raise RuntimeError(f'Installed example pin mismatch for {name}; do not flash')
    output.mkdir(parents=True,exist_ok=True)
    for name in ['app_httpd.cpp','camera_index.h','camera_pins.h','partitions.csv']:
        shutil.copy2(source/name,output/name)
    http_path = output/'app_httpd.cpp'
    http_source = http_path.read_text()
    marker = '  httpd_resp_set_hdr(req, "X-Timestamp", (const char *)ts);'
    capture_start = http_source.index("static esp_err_t capture_handler")
    capture_end = http_source.index("static esp_err_t stream_handler",capture_start)
    capture_source = http_source[capture_start:capture_end]
    if capture_source.count(marker)!=1:
        raise RuntimeError('Capture handler changed; inspect timestamp insertion before compiling')
    capture_source = capture_source.replace(marker,marker+'''
  // Report age using the camera's one monotonic clock, not a client epoch claim.
  char stride_age[32];
  int64_t stride_frame_us = (int64_t)fb->timestamp.tv_sec * 1000000LL + fb->timestamp.tv_usec;
  snprintf(stride_age, sizeof(stride_age), "%lld", (long long)(esp_timer_get_time()-stride_frame_us));
  httpd_resp_set_hdr(req, "X-Stride-Frame-Age-Us", stride_age);
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
''')
    http_path.write_text(http_source[:capture_start]+capture_source+http_source[capture_end:])
    sketch = (source/'CameraWebServer.ino').read_text()
    sketch = sketch.replace('const char *ssid = "**********";\nconst char *password = "**********";',
        '#include "secrets.h"\nconst char *ssid = STRIDE_CAMERA_WIFI_SSID;\nconst char *password = STRIDE_CAMERA_WIFI_PASSWORD;')
    if '#include "secrets.h"' not in sketch:
        raise RuntimeError('Installed example layout changed; inspect it before use')
    sketch = sketch.replace('  Serial.println();', '''  Serial.println();
  pinMode(48, INPUT);  // W11 RGB data is shared with camera Y9.
  if (String(ssid)=="YOUR_2_4_GHZ_WIFI") {
    Serial.println("Configure private secrets.h before camera WiFi use");
    for (;;) delay(1000);
  }''',1)
    sketch = sketch.replace('FRAMESIZE_UXGA','FRAMESIZE_VGA').replace('s->set_framesize(s, FRAMESIZE_QVGA)','s->set_framesize(s, FRAMESIZE_VGA)')
    (output/'CameraWebServer.ino').write_text(sketch)
    (output/'board_config.h').write_text(f'''// Vendor-documented W11 profile; physical board remains untested.
// {SOURCE}
#define CAMERA_MODEL_XIAO_ESP32S3
#include "camera_pins.h"
// No auxiliary LED/SD GPIO output in this camera-only bring-up.
#undef LED_GPIO_NUM
''')
    secrets = output/'secrets.h'
    if not secrets.exists():
        secrets.write_text('#pragma once\n#define STRIDE_CAMERA_WIFI_SSID "YOUR_2_4_GHZ_WIFI"\n#define STRIDE_CAMERA_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"\n')
        secrets.chmod(0o600)
    print(f'Prepared camera-only example: {output}')
    print(f'Edit WiFi privately in: {secrets}')
    print('Compile target: esp32:esp32:XIAO_ESP32S3:PSRAM=opi')
    print('Not flashed; no camera images or physical-board validation claimed.')


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core',type=Path,default=Path.home()/'Library/Arduino15/packages/esp32/hardware/esp32/3.3.2')
    parser.add_argument('--output',type=Path,default=Path('/tmp/stride-w11-camera/CameraWebServer'))
    args = parser.parse_args()
    prepare(args.core,args.output)
