# 华为应用市场 (Huawei AppGallery) 发布指南

应用：**鲸鱼随行** (`com.doctorai.app`)

## 发布清单

按顺序完成以下步骤：

### 第一阶段：准备工作（可并行）

- [ ] **1. 注册华为开发者账号** — [详见 01-developer-registration.md](./01-developer-registration.md)
  - 注册 AppGallery Connect 开发者账号
  - 完成实名认证（个人或企业）
  - 创建应用项目

- [ ] **2. 申请软件著作权（软著）** — [详见 02-software-copyright.md](./02-software-copyright.md)
  - 准备申请材料（源代码、说明书）
  - 提交至中国版权保护中心
  - 预计 1-2 个月（加急 3-7 天）

- [ ] **3. 准备隐私政策** — [详见 03-privacy-policy.md](./03-privacy-policy.md)
  - 编写符合《个人信息保护法》的隐私政策
  - 部署到可访问的 URL

### 第二阶段：构建

- [ ] **4. 构建签名 APK/AAB** — [详见 04-build-guide.md](./04-build-guide.md)
  - 构建 Android 发布包
  - 使用已有的 `doctorai-release.jks` 签名
  - 验证 APK 可正常安装运行

### 第三阶段：上架

- [ ] **5. 准备商店素材** — [详见 05-store-listing.md](./05-store-listing.md)
  - 应用图标（216x216）
  - 截图（至少 3 张）
  - 应用描述、简介
  - 分类选择

- [ ] **6. 提交审核** — [详见 06-submission-guide.md](./06-submission-guide.md)
  - 上传 APK/AAB
  - 填写应用信息
  - 提交华为审核（通常 1-3 个工作日）

## 项目信息速查

| 字段 | 值 |
|------|---|
| 应用 ID | `com.doctorai.app` |
| 应用名称 | 鲸鱼随行 |
| 版本号 | `versionCode 1` / `versionName 1.0` |
| 签名文件 | `frontend/web/android/app/doctorai-release.jks` |
| 最低 Android 版本 | minSdkVersion (见 `variables.gradle`) |
| API 地址 | 配置于 `.env.android` |
| 构建命令 | `npm run build:android && npx cap sync android` |
