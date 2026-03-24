# 构建签名 APK/AAB

## 前置条件

- Node.js 20+
- Android Studio (最新稳定版)
- Java 17+（Android Studio 自带）
- 已配置 `.env.android`（API 地址）

## 步骤

### 1. 配置 API 地址

```bash
cd frontend/web
cp .env.android.example .env.android
```

编辑 `.env.android`，填入生产环境 API 地址：

```
VITE_API_BASE_URL=https://api.doctoragentai.cn
```

### 2. 构建 Web 资源

```bash
npm run build:android    # 使用 android mode 构建前端
npx cap sync android     # 同步到 Android 项目
```

### 3. 更新版本号

编辑 `android/app/build.gradle`：

```gradle
defaultConfig {
    versionCode 1        // 每次提交商店必须递增
    versionName "1.0.0"  // 用户可见的版本号
}
```

> 华为商店要求每次更新 `versionCode` 必须大于上一次提交的值。

### 4. 构建签名 APK

#### 方式一：命令行（推荐）

```bash
cd android
./gradlew assembleRelease
```

输出位置：`android/app/build/outputs/apk/release/app-release.apk`

#### 方式二：构建 AAB（App Bundle）

```bash
cd android
./gradlew bundleRelease
```

输出位置：`android/app/build/outputs/bundle/release/app-release.aab`

> 华为应用市场同时支持 APK 和 AAB，推荐使用 APK（华为对 AAB 的支持不如 Google Play 完善）。

#### 方式三：Android Studio

1. 打开项目：`npx cap open android`
2. 菜单：Build → Generate Signed Bundle / APK
3. 选择 APK
4. Keystore: 选择 `app/doctorai-release.jks`
   - Store password: `doctorai2026`（或环境变量 `KEYSTORE_PASSWORD`）
   - Key alias: `doctorai`
   - Key password: `doctorai2026`（或环境变量 `KEY_PASSWORD`）
5. 选择 `release` Build Type → Finish

### 5. 验证 APK

```bash
# 检查 APK 签名
apksigner verify --print-certs android/app/build/outputs/apk/release/app-release.apk

# 安装到测试设备
adb install android/app/build/outputs/apk/release/app-release.apk
```

验证清单：
- [ ] 应用能正常启动
- [ ] 能正常登录
- [ ] API 请求正常（指向生产环境）
- [ ] 页面加载无白屏

## 签名信息

| 字段 | 值 |
|------|---|
| Keystore 文件 | `frontend/web/android/app/doctorai-release.jks` |
| Store Password | `doctorai2026`（建议迁移到环境变量） |
| Key Alias | `doctorai` |
| Key Password | `doctorai2026`（建议迁移到环境变量） |

> **安全提醒**：正式发布前应将密码从 `build.gradle` 硬编码迁移到环境变量或 `local.properties`（已 gitignore）。

## 常见问题

**Q: `capacitor.config.ts` 中的 `androidScheme: "https"` 是什么意思？**
A: 让 WebView 使用 https 协议加载本地资源，确保 cookies 和 auth headers 正常工作。

**Q: 构建时报 SDK 版本错误？**
A: 检查 `android/variables.gradle`，当前配置：`minSdk=23`, `compileSdk=35`, `targetSdk=35`。

**Q: 华为要求 targetSdk 最低版本？**
A: 华为目前要求 targetSdkVersion >= 31（Android 12）。当前配置 35，满足要求。
