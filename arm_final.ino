#include <Servo.h>
#include <ArduinoJson.h>

// ----------------- 新增: LED引脚定义 -----------------
const int LED1 = 2;
const int LED2 = 3;
const int LED3 = 4;
const int LED4 = 5;

Servo servo1;  
Servo servo2;  
Servo servoup;  
boolean stringComplete = false;
String inputString;  // 用来暂存接收到的原始JSON字符串

// 与原代码基本一致的变量声明
double rotate1;
double rotate2;
int updown;

double servo1Langle;
double servo2Langle;
double s1diff;
double s2diff;
double s1step;
double s2step;
int msdelay=2;

int pos;
int penpos;

// 几何及舵机控制参数
float baselen=4.5;
float arm1len=3.0;
float arm2len=6.0;
float selx;
float sely;
float pi=3.14159;

float baslenmid= baselen / 2;
float topstart= 3;
float arm3lens1;
float arm3lens2;

float S1angle;
float S2angle;
float C1angle;
float C2angle;

float S1Totangle;
float S2Totangle;
      
float initialangle=60;

void setup() {
  // ----------------- 新增: 初始化4个LED为输出 -----------------
  pinMode(LED1, OUTPUT);
  pinMode(LED2, OUTPUT);
  pinMode(LED3, OUTPUT);
  pinMode(LED4, OUTPUT);

  servo1.attach(10);
  servo2.attach(11);
  servoup.attach(9);
  delay(100);
  servo1Langle=120;
  servo2Langle=60;
  servo1.write(servo1Langle); 
  servo2.write(servo2Langle);
  servoup.write(10);
  penpos=0;

  Serial.begin(9600);
}

void loop() {
  // 当stringComplete为true，表示已接收到完整JSON数据并以'R'结束
  if (stringComplete == true) {
    // 使用ArduinoJson解析
    StaticJsonDocument<200> doc;  // 若有需要可改大，比如 500
    DeserializationError error = deserializeJson(doc, inputString);

    if (!error) {
      // 解析成功
      rotate1 = doc["x"];
      rotate2 = doc["y"];
      updown = doc["updown"];
      
      // 将坐标转换为机械臂的空间坐标体系
      selx=(rotate1/50.0)+baslenmid;
      sely=(rotate2/50.0)+topstart;

      anglecalc();  // 与原函数保持一致
      S1Totangle=S1Totangle-initialangle;
      S2Totangle=180-(S2Totangle-initialangle);

      // 与原逻辑保持一致：检查角度范围，控制舵机移动
      if(S1Totangle>=0 && S1Totangle<=180 && S2Totangle>=0 && S2Totangle<=180) {
        s1diff=servo1Langle-S1Totangle;
        s2diff=servo2Langle-S2Totangle;

        if(abs(s1diff)>abs(s2diff)) {
          s1step=s1diff/abs(s1diff);
          s2step=s2diff/abs(s1diff);
          for (pos = 0; pos <= abs(s1diff); pos += 1) { 
            servo1Langle=servo1Langle-s1step;
            servo2Langle=servo2Langle-s2step;
            servo1.write(servo1Langle); 
            servo2.write(servo2Langle);
            delay(msdelay);                       
          }   
          servo1.write(S1Totangle); 
          servo2.write(S2Totangle);                
        } else if(abs(s2diff)>0) {
          s1step=s1diff/abs(s2diff);
          s2step=s2diff/abs(s2diff);            
          for (pos = 0; pos <= abs(s2diff); pos += 1) { 
            servo1Langle=servo1Langle-s1step;
            servo2Langle=servo2Langle-s2step;
            servo1.write(servo1Langle); 
            servo2.write(servo2Langle);  
            delay(msdelay);                       
          }                      
          servo1.write(S1Totangle); 
          servo2.write(S2Totangle); 
        }

        servo1Langle=S1Totangle;
        servo2Langle=S2Totangle;

        // 控制笔的上下 (或多档位)
        if (updown != penpos) {
          penpos = updown;
          penupdown();
        }
      } else {
        // 如果角度超出范围，考虑抬笔或其他安全处理
        if (penpos == 1) {
          penpos = 0;      
          penupdown();
        }
      }

      // ★★★ 解析成功后，打印换行版 "N" ★★★
      Serial.println("N");  

    } else {
      // ★★★ 解析失败时，打印整行错误信息 ★★★
      Serial.println("JSON parse error");
    }

    // 清空输入缓存
    inputString = "";
    stringComplete = false;
  }

  // ----------------- 新增: LED循环亮灭 -----------------
  blinkLeds();
}

// ========== 多档位笔上下函数 ==========
void penupdown() {
  // 在这里添加调试输出
  Serial.print("[DEBUG] penupdown called, penpos = ");
  Serial.println(penpos);

  // 定义舵机的目标角度
  int targetAngle;

  if (penpos == 0) {
    // 笔完全抬起
    targetAngle = 5; 
  } else if (penpos == 1) {
    // 完全放下
    targetAngle = 50; 
  } else if (penpos == 2) {
    // 比完全放下高一点（举例：高10度）
    targetAngle = 45; 
  } else if (penpos == 3) {
    // 比完全放下高更多（举例：高20度）
    targetAngle = 40; 
  } else {
    // 其它未知值，防御性处理 => 抬起
    targetAngle = 5;
  }

  // 获取当前舵机角度 (近似)
  int currentAngle = servoup.read();


  if (targetAngle > currentAngle) {
    for (int p = currentAngle; p <= targetAngle; p++) {
      servoup.write(p);
      delay(msdelay);
    }
  } else {
    for (int p = currentAngle; p >= targetAngle; p--) {
      servoup.write(p);
      delay(msdelay);
    }
  }
}

void anglecalc() {
  arm3lens1 = sqrt((pow((selx - 0), 2)) + (pow((sely - 0), 2)));
  arm3lens2 = sqrt((pow((selx - baselen), 2)) + (pow((sely - 0), 2)));
  
  S1angle = findangle(arm1len, arm3lens1, arm2len);
  S2angle = findangle(arm1len, arm3lens2, arm2len);
  C1angle = findangle(baselen, arm3lens1, arm3lens2);
  C2angle = findangle(baselen, arm3lens2, arm3lens1);

  S1Totangle = round((S1angle + C1angle)*100)/100.00;
  S2Totangle = round((S2angle + C2angle)*100)/100.00;
}

float findangle(float opp, float adj, float hyp) {
  float Scal2 = (pow(opp, 2) + pow(adj, 2) - pow(hyp, 2)) / (2.0 * opp * adj);
  float Scal = acos(Scal2);
  Scal = findangle(Scal);
  return Scal;
}

float findangle(float radians) {
  float degree;
  degree = radians * (180 / 3.14159);
  return degree;
}

void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();   
    if (inChar == 'R') {
      stringComplete = true;
    } else {
      inputString += inChar; 
    }
  }    
}

void blinkLeds() {
  digitalWrite(LED1, HIGH);   delay(500);
  digitalWrite(LED2, HIGH);   delay(500);
  digitalWrite(LED3, HIGH);   delay(500);
  digitalWrite(LED4, HIGH);   delay(500);

  digitalWrite(LED1, LOW);    delay(500);
  digitalWrite(LED2, LOW);    delay(500);
  digitalWrite(LED3, LOW);    delay(500);
  digitalWrite(LED4, LOW);    delay(500);
}
