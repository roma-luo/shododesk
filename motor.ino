/***************************************************
 * Arduino Code (添加马达 D，与 A、B 同步转动，且A再单独逆转一半时间)
 *
 * 逻辑：
 *   1) "AB <秒数>"：
 *       - (a) 马达 A、B、D 同方向旋转 <秒数> 秒
 *       - (b) B、D 停止；A 反转 <秒数> / 2
 *       - (c) A 停止，打印 "Done"
 *
 *   2) "C" 命令：
 *       - 保持原逻辑 (6 段正转 + 一次性反转)
 ***************************************************/

// ========== 马达 A、B (第一颗 L293D) ==========
const int enablePin12 = 9;   // 给通道1,2 (A,B) 的 Enable (PWM)
const int motorA1 = 2;       // A 通道输入脚1A
const int motorA2 = 3;       // A 通道输入脚2A
const int motorB1 = 4;       // B 通道输入脚3A
const int motorB2 = 5;       // B 通道输入脚4A

// ========== 马达 C、D (第二颗 L293D) ==========
// 注意：马达 C 已用 1A,2A => Arduino 脚 6,7
// 我们把 D 用 3A,4A => Arduino 脚 12,13
const int enablePinCD = 9;   // 同样接到 Arduino Pin9 (与 A,B 的使能同线)
const int motorC1 = 6;       // C 通道输入脚 (1A)
const int motorC2 = 7;       // C 通道输入脚 (2A)
// C 输出 (1Y, 2Y) => L293D Pin3, Pin6

// 新增马达 D
const int motorD1 = 12;      // D 通道输入脚 (3A)
const int motorD2 = 13;      // D 通道输入脚 (4A)
// D 输出 (3Y, 4Y) => L293D Pin11, Pin14

// ========== 供马达 C 用的分段延时 ==========
const unsigned long DELAY_60_DEG = 30; 

// ========== 马达 C,D 的初始 PWM ==========
const int speedC = 128;

void setup() {
  Serial.begin(9600);

  // ========== 马达 A、B 初始化 (第一颗 L293D) ==========
  pinMode(enablePin12, OUTPUT);
  pinMode(motorA1, OUTPUT);
  pinMode(motorA2, OUTPUT);
  pinMode(motorB1, OUTPUT);
  pinMode(motorB2, OUTPUT);

  // 让马达 A,B 全速 (或可用 analogWrite)
  analogWrite(enablePin12, 255);

  // ========== 马达 C、D 初始化 (第二颗 L293D) ==========
  // C 用 1A,2A => 脚 6,7；D 用 3A,4A => 脚 12,13
  pinMode(enablePinCD, OUTPUT);
  pinMode(motorC1, OUTPUT);
  pinMode(motorC2, OUTPUT);
  pinMode(motorD1, OUTPUT);
  pinMode(motorD2, OUTPUT);

  // 让马达 C,D 也全速 (与 A,B 同脚 Pin9)
  analogWrite(enablePinCD, speedC);
}

void loop() {
  // 如果串口无数据就不做事
  if (Serial.available() <= 0) {
    return;
  }

  // 读取一整行命令
  String commandLine = Serial.readStringUntil('\n');
  commandLine.trim();
  if (commandLine.length() == 0) return;

  // 拆分指令
  int spaceIndex = commandLine.indexOf(' ');
  String cmd;
  String param;
  if (spaceIndex == -1) {
    cmd = commandLine; // 可能是 "C"
  } else {
    cmd   = commandLine.substring(0, spaceIndex);
    param = commandLine.substring(spaceIndex + 1);
  }
  cmd.toUpperCase();

  // ========== 处理 "AB <秒数>" ==========
  if (cmd == "AB") {
    float seconds = param.toFloat();
    if (seconds <= 0) {
      Serial.println("Done"); 
      return;
    }

    // (a) 马达 A、B、D 同方向转 <秒数> 秒
    digitalWrite(motorA1, HIGH);
    digitalWrite(motorA2, LOW);

    digitalWrite(motorB1, HIGH);
    digitalWrite(motorB2, LOW);

    digitalWrite(motorD1, LOW);
    digitalWrite(motorD2, HIGH);

    unsigned long ms = (unsigned long)(seconds * 1000);
    delay(ms);

    // 停止 B、D
    digitalWrite(motorB1, LOW);
    digitalWrite(motorB2, LOW);
    digitalWrite(motorD1, LOW);
    digitalWrite(motorD2, LOW);
    // A 此时仍要进行额外的逆向旋转

    // (b) A 逆向旋转 <秒数>/2
    digitalWrite(motorA1, LOW);
    digitalWrite(motorA2, HIGH);

    unsigned long halfMs = ms / 2; // 一半时间
    delay(halfMs);

    // (c) 最后停止 A
    digitalWrite(motorA1, LOW);
    digitalWrite(motorA2, LOW);

    Serial.println("Done");
  }
  // ========== 处理 "C" 命令 (马达 C 分段旋转 + 拍照) ==========
  else if (cmd == "C") {
    // (1) 分 6 段正转
    for (int i = 0; i < 6; i++) {
      // a) 转 60°
      digitalWrite(motorC1, HIGH);
      digitalWrite(motorC2, LOW);
      delay(DELAY_60_DEG);

      // b) 停止
      digitalWrite(motorC1, LOW);
      digitalWrite(motorC2, LOW);

      // c) 等 1.5 秒 (拍照之类)
      delay(1500);

      // d) 告诉 Python "C_STEP"
      Serial.println("C_STEP");

      // e) 等 Python 回 "CONTINUE"
      bool waiting = true;
      while (waiting) {
        if (Serial.available() > 0) {
          String ack = Serial.readStringUntil('\n');
          ack.trim();
          if (ack.equalsIgnoreCase("CONTINUE")) {
            waiting = false;
          }
        }
        delay(10);
      }
    }

    // (2) 一次性反转 360°
    digitalWrite(motorC1, LOW);
    digitalWrite(motorC2, HIGH);
    delay(6 * DELAY_60_DEG);

    // 停止
    digitalWrite(motorC1, LOW);
    digitalWrite(motorC2, LOW);

    Serial.println("Done");
  }
  // ========== 其它未知命令 ==========
  else {
    Serial.println("Done"); 
  }
}
