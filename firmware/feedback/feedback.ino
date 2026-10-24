// Independent local loop; bounded TLS work runs on a separate FreeRTOS task.
// GPIO19 MUST receive divided ECHO; GPIO25 drives protected regulated 3 V motor.
#include <Arduino.h>
#include "controller.h"
#include "stride_network.h"
stride::Controller feedback;
RemoteCue activeCue{};
bool hasActive=false;

void queueAck(const RemoteCue& cue, const char* status) {
  DeviceAck ack{};
  strlcpy(ack.id,cue.id,sizeof(ack.id)); strlcpy(ack.generation,cue.generation,sizeof(ack.generation));
  strlcpy(ack.status,status,sizeof(ack.status));
  if(xQueueSend(ackQueue,&ack,0)!=pdTRUE) Serial.println("ACK buffer full; delivery unverified");
}
void cancelActive(const char* status) {
  feedback.cancel();
  if(hasActive) { queueAck(activeCue,status); hasActive=false; }
}
constexpr int TRIG=18, ECHO=19, BUZZER=23, MOTOR=25;
portMUX_TYPE echoLock=portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t rising=0, duration=0;
volatile bool complete=false;
uint32_t lastTrigger=0, triggerMicros=0;
bool waiting=false, highTrigger=false;

void IRAM_ATTR echoEdge() {
  portENTER_CRITICAL_ISR(&echoLock);
  if (digitalRead(ECHO)) rising=micros();
  else { duration=micros()-rising; complete=true; }
  portEXIT_CRITICAL_ISR(&echoLock);
}
void setup() {
  Serial.begin(115200);
  commandQueue=xQueueCreate(1,sizeof(RemoteCue)); ackQueue=xQueueCreate(8,sizeof(DeviceAck));
  if(!commandQueue || !ackQueue) { Serial.println("Queue allocation failed; outputs disabled"); for(;;) delay(1000); }
  bootId=randomUuid();
  pinMode(TRIG,OUTPUT); pinMode(ECHO,INPUT);
  pinMode(BUZZER,OUTPUT); pinMode(MOTOR,OUTPUT);
  digitalWrite(TRIG,LOW); digitalWrite(BUZZER,LOW); digitalWrite(MOTOR,LOW);
  attachInterrupt(digitalPinToInterrupt(ECHO),echoEdge,CHANGE);
  if(STRIDE_NETWORK_CONFIGURED) {
    if(xTaskCreatePinnedToCore(networkTask,"stride-network",12288,nullptr,1,nullptr,0)!=pdPASS) Serial.println("Network task unavailable; local sensing remains active");
  } else Serial.println("Local-only mode: network config absent");
}
void loop() {
  uint32_t now=millis(), us=micros();
  if (!waiting && now-lastTrigger>=100) {
    portENTER_CRITICAL(&echoLock); complete=false; portEXIT_CRITICAL(&echoLock);
    digitalWrite(TRIG,HIGH); triggerMicros=us; highTrigger=true; waiting=true; lastTrigger=now;
  }
  if(highTrigger && us-triggerMicros>=10) { digitalWrite(TRIG,LOW); highTrigger=false; }
  bool ready; uint32_t pulse;
  portENTER_CRITICAL(&echoLock); ready=complete; pulse=duration; complete=false; portEXIT_CRITICAL(&echoLock);
  if(waiting && ready) { feedback.sample(pulse*.0343f/2, pulse>0 && pulse<30000,now); waiting=false; }
  else if(waiting && us-triggerMicros>=30000) { feedback.sample(0,false,now); waiting=false; }
  uint32_t health=healthyAt.load();
  if(!health || now-health>1000) cancelActive("rejected");
  RemoteCue cue{};
  if(xQueueReceive(commandQueue,&cue,0)==pdTRUE) {
    if(!cue.id[0]) cancelActive("rejected");
    else {
      cancelActive("rejected");
      uint32_t elapsed=cue.elapsed+(now-cue.received);
      bool accepted=health && now-health<=1000 && feedback.command(cue.id,cue.pattern,cue.ttl,elapsed,now);
      queueAck(cue,accepted?"accepted":(cue.ttl<=elapsed?"expired":"rejected"));
      if(accepted) { activeCue=cue; activeCue.received=now; activeCue.ttl=cue.ttl-elapsed; hasActive=true; }
    }
  }
  auto output=feedback.tick(now);
  if(hasActive && !feedback.remoteActive()) {
    const char* status=output.band!=stride::Band::Clear?"rejected":now-activeCue.received>=activeCue.ttl?"expired":"completed";
    queueAck(activeCue,status); hasActive=false;
  }
  portENTER_CRITICAL(&snapshotLock);
  sensorSnapshot.valid=output.band!=stride::Band::Unknown;
  sensorSnapshot.cm=feedback.distanceCm(); sensorSnapshot.band=output.band;
  strlcpy(sensorSnapshot.active,hasActive?activeCue.id:"",sizeof(sensorSnapshot.active));
  portEXIT_CRITICAL(&snapshotLock);
  digitalWrite(MOTOR,output.motor); digitalWrite(BUZZER,output.buzzer);
  // No network/TLS call is allowed on this local timing loop.
}
