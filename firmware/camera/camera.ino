// W11 board gate is deliberate. Syntax-only builds never initialize hardware.
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <esp_camera.h>
#include <esp_timer.h>
#include <time.h>
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif
#if !defined(STRIDE_CAMERA_COMPILE_ONLY)
#if __has_include("board_config.h")
#include "board_config.h"
#else
#include "board_config.example.h"
#endif
#endif

String bootId;
uint32_t sequence=0,lastReconnect=0;
uint64_t lastStateSeq=0;
int revision=-1;
int64_t serverOffset=0;
bool selected=false,active=false;

String uuid() {
  char out[37];
  snprintf(out,sizeof(out),"%08lx-%04x-4%03x-a%03x-%04x%08lx",
           (unsigned long)esp_random(),(unsigned)(esp_random()&65535),
           (unsigned)(esp_random()&4095),(unsigned)(esp_random()&4095),
           (unsigned)(esp_random()&65535),(unsigned long)esp_random());
  return String(out);
}

bool pollCameraState() {
  active=false; selected=false;
  if(WiFi.status()!=WL_CONNECTED || time(nullptr)<1700000000) return false;
  WiFiClientSecure tls; tls.setCACert(STRIDE_ROOT_CA); tls.setHandshakeTimeout(2);
  HTTPClient http; http.setConnectTimeout(300); http.setTimeout(300);
  String path=String(STRIDE_BASE_URL)+"/devices/"+STRIDE_DEVICE_ID+"/camera-state?session_id="+STRIDE_SESSION_ID;
  if(!http.begin(tls,path)) return false;
  http.addHeader("Authorization",String("Bearer ")+STRIDE_DEVICE_TOKEN);
  int64_t before=esp_timer_get_time()/1000;
  int code=http.GET();
  bool ok=false;
  if(code==200 && http.getSize()>0 && http.getSize()<=2048) {
    String body=http.getString();
    int64_t after=esp_timer_get_time()/1000;
    JsonDocument state;
    if(body.length()<=2048 && after-before<=200 && !deserializeJson(state,body)
       && String(state["session_id"] | "")==STRIDE_SESSION_ID
       && String(state["device_id"] | "")==STRIDE_DEVICE_ID
       && state["source_revision"].is<int>() && state["server_time_ms"].is<int64_t>()
       && state["state_seq"].is<uint64_t>() && state["state_seq"].as<uint64_t>()>=lastStateSeq
       && state["source_revision"].as<int>()>=revision) {
      lastStateSeq=state["state_seq"].as<uint64_t>();
      revision=state["source_revision"].as<int>();
      serverOffset=state["server_time_ms"].as<int64_t>()-(before+after)/2;
      selected=state["selected"] | false; active=state["active"] | false;
      ok=true;
    }
  }
  http.end(); return ok;
}

bool upload(camera_fb_t* fb,int64_t capturedMs) {
  if(!active || !selected || revision<0 || !fb || fb->len>1000000 || fb->format!=PIXFORMAT_JPEG) return false;
  if(esp_timer_get_time()/1000+serverOffset-capturedMs>=1000) return false;
  WiFiClientSecure tls; tls.setCACert(STRIDE_ROOT_CA); tls.setHandshakeTimeout(2);
  HTTPClient http; http.setConnectTimeout(300); http.setTimeout(300);
  if(!http.begin(tls,String(STRIDE_BASE_URL)+"/frame")) return false;
  http.addHeader("Authorization",String("Bearer ")+STRIDE_DEVICE_TOKEN);
  http.addHeader("Content-Type","image/jpeg");
  http.addHeader("X-Session-Id",STRIDE_SESSION_ID); http.addHeader("X-Device-Id",STRIDE_DEVICE_ID);
  http.addHeader("X-Boot-Id",bootId); http.addHeader("X-Sequence",String(++sequence));
  http.addHeader("X-Frame-Id",uuid()); http.addHeader("X-Source-Revision",String(revision));
  char captured[24]; snprintf(captured,sizeof(captured),"%lld",(long long)capturedMs);
  http.addHeader("X-Captured-Ms",captured); http.addHeader("X-Clock-Synced","true");
  int code=http.POST(fb->buf,fb->len);
  http.end();
  if(code<200 || code>=300) { active=false; return false; }
  return true;
}

bool initCamera() {
#if defined(STRIDE_CAMERA_COMPILE_ONLY)
  return false;
#else
  static_assert(STRIDE_W11_VERIFIED,"Exact W11 board configuration required");
  static_assert(W11_XCLK_HZ>0,"Use the verified vendor XCLK frequency");
  if(W11_USE_PSRAM && !psramFound()) return false;
  camera_config_t c={};
  c.ledc_channel=LEDC_CHANNEL_0; c.ledc_timer=LEDC_TIMER_0;
  c.pin_d0=W11_D0; c.pin_d1=W11_D1; c.pin_d2=W11_D2; c.pin_d3=W11_D3;
  c.pin_d4=W11_D4; c.pin_d5=W11_D5; c.pin_d6=W11_D6; c.pin_d7=W11_D7;
  c.pin_xclk=W11_XCLK; c.pin_pclk=W11_PCLK; c.pin_vsync=W11_VSYNC; c.pin_href=W11_HREF;
  c.pin_sccb_sda=W11_SDA; c.pin_sccb_scl=W11_SCL; c.pin_pwdn=W11_PWDN; c.pin_reset=W11_RESET;
  c.xclk_freq_hz=W11_XCLK_HZ; c.pixel_format=PIXFORMAT_JPEG;
  c.frame_size=FRAMESIZE_VGA; c.jpeg_quality=12; c.fb_count=1;
  c.fb_location=W11_USE_PSRAM?CAMERA_FB_IN_PSRAM:CAMERA_FB_IN_DRAM;
  c.grab_mode=CAMERA_GRAB_LATEST;
  if(esp_camera_init(&c)!=ESP_OK) return false;
  sensor_t* sensor=esp_camera_sensor_get();
  if(!sensor || sensor->id.PID!=OV3660_PID) return false;
  sensor->set_hmirror(sensor,W11_HMIRROR); sensor->set_vflip(sensor,W11_VFLIP);
  return true;
#endif
}

void setup() {
  Serial.begin(115200);
  if(!initCamera()) { Serial.println("Camera blocked: board/sensor/config not verified"); for(;;) delay(1000); }
  bootId=uuid();
  if(!STRIDE_NETWORK_CONFIGURED || !String(STRIDE_BASE_URL).startsWith("https://") || !strlen(STRIDE_ROOT_CA)) {
    Serial.println("Network config absent; uploader disabled"); for(;;) delay(1000);
  }
  WiFi.mode(WIFI_STA); WiFi.begin(STRIDE_WIFI_SSID,STRIDE_WIFI_PASSWORD);
  configTime(0,0,"pool.ntp.org","time.nist.gov");
}
void loop() {
  uint32_t began=millis();
  if(WiFi.status()!=WL_CONNECTED) {
    active=false;
    if(millis()-lastReconnect>3000) { WiFi.reconnect(); lastReconnect=millis(); }
    delay(100); return;
  }
  // Poll every capture. Inactive/unreachable state never uploads cached frames.
  if(!pollCameraState() || !active || !selected) { delay(200); return; }
  camera_fb_t* fb=esp_camera_fb_get();
  if(fb) {
    int64_t captureBootMs=(int64_t)fb->timestamp.tv_sec*1000+fb->timestamp.tv_usec/1000;
    // Driver timestamp is monotonic since boot; align using measured server RTT.
    int64_t age=esp_timer_get_time()/1000-captureBootMs;
    if(age>=0 && age<1000) upload(fb,captureBootMs+serverOffset);
    esp_camera_fb_return(fb); // All capture paths release the single buffer.
  }
  uint32_t elapsed=millis()-began;
  if(elapsed<200) delay(200-elapsed);
}
