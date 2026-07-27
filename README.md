# ORVIBO Cloud for Home Assistant

**欧瑞博 HomeMate / 智家365 云端设备接入 Home Assistant**

[GitHub Releases](https://github.com/maycode0-0/orvibo-cloud/releases) |
[HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=maycode0-0&repository=orvibo-cloud&category=integration) |
[MIT License](LICENSE)

[简体中文](#简体中文) | [English](#english)

---

## 简体中文

> [!WARNING]
> 这是一个实验性的非官方集成，依赖欧瑞博私有云 API。欧瑞博调整接口后，集成可能会停止工作。

ORVIBO Cloud 可将 **HomeMate** 或 **智家365** 账号中的设备接入 Home Assistant。集成会自动探测账号所在区域的云端节点，通过 REST API 获取家庭、房间和设备信息，并通过欧瑞博的双向 TLS 二进制云协议控制已验证的设备。

### 功能

- 自动探测中国、HomeMate、德国和美国区域节点
- 支持账号登录、多个家庭选择和凭据失效后的重新认证
- 从云端读取完整设备列表，由用户选择需要接入 Home Assistant 的设备
- 自动使用欧瑞博 App 中的房间作为默认区域，也可在配置时或集成选项中修改
- 支持已验证的窗帘电机和灯光设备控制
- 提供云端连接状态、当前家庭和设备数量等诊断实体
- 每 30 分钟刷新一次云端设备状态，控制命令执行后会立即更新实体状态
- 不保存明文密码；二进制会话密码仅保存在内存中

### 工作原理

```text
┌──────────────────┐       HTTPS / REST        ┌──────────────────┐
│ Home Assistant   │ ────────────────────────> │ ORVIBO regional  │
│ / orvibo_cloud   │ <──────────────────────── │ cloud endpoint   │
│                  │   家庭、房间、设备及状态    │                  │
│                  │                            │                  │
│                  │   mutual TLS / TCP 10002  │                  │
│                  │ ────────────────────────> │ Binary cloud     │
│                  │ <──────────────────────── │ service          │
└──────────────────┘       控制结果             └──────────────────┘
```

1. 自动尝试可用的区域节点，并通过 `/getOauthToken` 登录。
2. 获取账号下的家庭列表，并通过 `/v2/cmd/app/readtable` 下载设备表。
3. 将用户选择的设备及其房间信息注册到 Home Assistant。
4. 通过端口 `10002` 上的双向 TLS 二进制协议发送已验证的控制命令。
5. 定期从设备表刷新状态；部分控制后的状态在下一次刷新前为乐观更新。

### 安装

#### 方式一：通过 HACS（推荐）

[在 HACS 中打开此仓库](https://my.home-assistant.io/redirect/hacs_repository/?owner=maycode0-0&repository=orvibo-cloud&category=integration)

1. 在 HACS 中添加自定义仓库：`https://github.com/maycode0-0/orvibo-cloud`
2. 仓库类型选择 **Integration**，然后搜索并安装 **ORVIBO Cloud**
3. 重启 Home Assistant
4. 进入 **设置 > 设备与服务 > 添加集成**，搜索 **ORVIBO Cloud**

通过 HACS 安装后，新版本发布时会在 Home Assistant 中显示更新提醒。每次发布都必须提升 `custom_components/orvibo_cloud/manifest.json` 中的版本号；合入 `main` 后，仓库会自动创建对应的 GitHub Tag 和 Release。

#### 方式二：手动安装

将本仓库中的 `custom_components/orvibo_cloud/` 复制到 Home Assistant 配置目录：

```text
config/
└── custom_components/
    └── orvibo_cloud/
```

重启 Home Assistant，然后进入 **设置 > 设备与服务 > 添加集成**，搜索 **ORVIBO Cloud**。

### 配置

| 项目 | 必填 | 说明 |
|:-----|:----:|:-----|
| 邮箱或账号 | 是 | HomeMate 或智家365使用的登录账号 |
| 密码 | 是 | 对应账号密码，仅在提交配置时用于生成登录所需的哈希 |
| 家庭 | 多家庭账号需要 | 账号下只有一个家庭时自动选择 |
| 设备 | 是 | 只有勾选的设备才会注册到 Home Assistant |
| 区域 | 否 | 默认使用欧瑞博 App 中的房间，可改为任意 Home Assistant 区域 |

安装完成后，可在集成的 **配置** 对话框中重新选择设备和区域。账号密码失效时，Home Assistant 会启动重新认证流程。

### 支持的设备

只有经过抓包验证的设备配置才会创建可控制实体。其他选中的设备仍会出现在 Home Assistant 设备注册表中，但不会自动获得控制实体。

| 类别 | 已验证配置 | Home Assistant 功能 |
|:-----|:-----------|:--------------------|
| 窗帘 | `type=34` | 打开、关闭、停止、位置控制 |
| 开关型灯光 | `type=1/subtype=1`、`type=102/subtype=1` | 开、关 |
| 调光调色温灯 | `type=38/subtype=4,6,13` | 开、关、亮度、色温 |
| 属性型筒灯/灯带 | 已抓包验证的 `type=503/subtype=436` 型号 | 开、关、亮度、色温 |
| 巨目 2K S1 摄像头 | 设备发现与注册 | 暂无 `camera` 实体 |

> [!NOTE]
> 巨目 2K S1 的视频使用 Meari 加密 ICE/P2P 协议，不是 RTSP 或 ONVIF。设备可被发现并注册，但视频接入需要独立的 Meari 协议实现。

### 诊断实体

- **连接**：最近一次已认证云端刷新是否成功
- **家庭**：当前选择的欧瑞博家庭
- **设备**：云端返回的设备数量及设备类型

### 技术细节

- **集成类型**：Cloud Polling
- **状态刷新间隔**：30 分钟
- **登录接口**：`GET https://<region>.orvibo.com/getOauthToken`
- **家庭接口**：`POST https://<region>.orvibo.com/v2/family/statistics/users`
- **设备发现**：`POST https://<region>.orvibo.com/v2/cmd/app/readtable`
- **设备控制**：双向 TLS，TCP 端口 `10002`
- **区域同步**：读取设备表中的房间并映射到 Home Assistant 区域

### 安全说明

- 集成不会保存明文密码，而是保存欧瑞博接口要求的**大写 MD5 凭据**。该值与密码等效，仍应严格保密。
- `readtable` 返回的二进制会话密码仅保存在内存中，不会出现在诊断信息或对象表示中。
- 不要记录 OAuth 响应、密码哈希或其他账号令牌。
- 即使敏感字段已被清理，也应将 Home Assistant 诊断导出视为私密数据。
- 端口 `10002` 使用已由致谢项目公开的旧版欧瑞博客户端证书和私钥。请勿将其用于控制本人欧瑞博账号以外的任何服务。

### 开发与验证

运行不依赖 Home Assistant 安装环境的协议测试：

```powershell
python -m unittest discover -s tests -v
```

项目主要结构：

```text
orvibo-cloud/
├── custom_components/orvibo_cloud/
│   ├── api.py               # REST 登录与设备表获取
│   ├── binary.py            # 双向 TLS 二进制云协议
│   ├── config_flow.py       # UI 配置、设备及区域选择
│   ├── coordinator.py       # 云端状态刷新
│   ├── cover.py             # 窗帘实体
│   ├── light.py             # 灯光实体
│   ├── sensor.py            # 诊断传感器
│   └── translations/        # 多语言翻译
├── tests/
├── hacs.json
└── README.md
```

### 致谢

协议行为通过实际抓包以及 MIT 许可的 [`orvibo-homeassistant-curtains`](https://github.com/kjanko/orvibo-homeassistant-curtains) 项目进行交叉验证。

---

## English

> [!WARNING]
> This is an experimental, unofficial integration built on ORVIBO's private cloud APIs. It may stop working if ORVIBO changes those APIs.

ORVIBO Cloud connects devices from a **HomeMate** or **ZhiJia365** account to Home Assistant. It discovers the account's regional endpoint, retrieves family, room, and device data through the REST API, and controls verified devices through ORVIBO's mutual-TLS binary cloud protocol.

### Features

- Discovers the China, HomeMate, Germany, or USA regional endpoint
- Supports account authentication, multiple-family selection, and Home Assistant reauthentication
- Downloads the complete cloud device table and lets you choose which devices to add
- Uses ORVIBO rooms as default Home Assistant areas, with area selection during setup or later in the integration options
- Controls verified curtain motors and light profiles
- Exposes cloud connectivity, selected family, and device count as diagnostic entities
- Refreshes cloud device state every 30 minutes and updates entity state immediately after control commands
- Never stores the plaintext password; the binary session password remains in memory only

### How it works

```text
┌──────────────────┐       HTTPS / REST        ┌──────────────────┐
│ Home Assistant   │ ────────────────────────> │ ORVIBO regional  │
│ / orvibo_cloud   │ <──────────────────────── │ cloud endpoint   │
│                  │  families, rooms, devices │                  │
│                  │                            │                  │
│                  │   mutual TLS / TCP 10002  │                  │
│                  │ ────────────────────────> │ Binary cloud     │
│                  │ <──────────────────────── │ service          │
└──────────────────┘      command result        └──────────────────┘
```

1. The integration tries the configured regional endpoints and authenticates through `/getOauthToken`.
2. It retrieves the account families and downloads the device table from `/v2/cmd/app/readtable`.
3. Selected devices and their room information are registered with Home Assistant.
4. Verified commands are sent through the mutual-TLS binary service on port `10002`.
5. State is periodically refreshed from the device table; some command results are optimistic until the next refresh.

### Installation

#### Option 1: HACS (recommended)

[Open this repository in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=maycode0-0&repository=orvibo-cloud&category=integration)

1. Add `https://github.com/maycode0-0/orvibo-cloud` to HACS as a custom **Integration** repository.
2. Search for and install **ORVIBO Cloud**.
3. Restart Home Assistant.
4. Open **Settings > Devices & services > Add integration** and search for **ORVIBO Cloud**.

After installation through HACS, Home Assistant will show an update when a new version is released. Every release must increment the version in `custom_components/orvibo_cloud/manifest.json`; merging it into `main` automatically creates the matching GitHub tag and release.

#### Option 2: Manual installation

Copy `custom_components/orvibo_cloud/` from this repository into your Home Assistant configuration directory:

```text
config/
└── custom_components/
    └── orvibo_cloud/
```

Restart Home Assistant, then open **Settings > Devices & services > Add integration** and search for **ORVIBO Cloud**.

### Configuration

| Field | Required | Description |
|:------|:--------:|:------------|
| Email or account | Yes | The account used by HomeMate or ZhiJia365 |
| Password | Yes | Used only at submission time to generate the credential hash required for login |
| Family | For multi-family accounts | Automatically selected when the account has only one family |
| Devices | Yes | Only selected devices are registered with Home Assistant |
| Area | No | Defaults to the room from the ORVIBO app and can be changed to any Home Assistant area |

After setup, open the integration's **Configure** dialog to change the selected devices or their areas. Home Assistant starts a reauthentication flow if the saved credentials are rejected.

### Supported devices

Controllable entities are created only for packet-capture-verified profiles. Other selected devices are still added to the Home Assistant Device Registry, but they do not automatically receive control entities.

| Category | Verified profile | Home Assistant features |
|:---------|:-----------------|:------------------------|
| Curtains | `type=34` | Open, close, stop, and position |
| Relay lights | `type=1/subtype=1`, `type=102/subtype=1` | On and off |
| Tunable-white lights | `type=38/subtype=4,6,13` | On, off, brightness, and color temperature |
| Property-based downlights/light strips | Captured `type=503/subtype=436` models | On, off, brightness, and color temperature |
| Giant Eye 2K S1 camera | Discovery and device registration | No `camera` entity |

> [!NOTE]
> Giant Eye 2K S1 video uses Meari's encrypted ICE/P2P protocol rather than RTSP or ONVIF. The device can be discovered and registered, but video support requires a separate Meari protocol implementation.

### Diagnostic entities

- **Connection**: whether the latest authenticated cloud refresh succeeded
- **Family**: the currently selected ORVIBO family
- **Devices**: the number and types of devices returned by the cloud

### Technical details

- **Integration type**: Cloud Polling
- **State refresh interval**: 30 minutes
- **Login endpoint**: `GET https://<region>.orvibo.com/getOauthToken`
- **Family endpoint**: `POST https://<region>.orvibo.com/v2/family/statistics/users`
- **Device discovery**: `POST https://<region>.orvibo.com/v2/cmd/app/readtable`
- **Device control**: mutual TLS on TCP port `10002`
- **Area synchronization**: maps rooms from the device table to Home Assistant areas

### Security

- The integration stores the **uppercase MD5 credential** required by ORVIBO instead of the plaintext password. Treat this value as password-equivalent and keep it private.
- The separate binary-session password returned by `readtable` is held in memory only and excluded from diagnostics and object representations.
- Do not log OAuth responses, the password hash, or other account tokens.
- Treat Home Assistant diagnostics exports as private even though sensitive values are redacted.
- Port `10002` uses a legacy ORVIBO client certificate and private key already published by the acknowledged project. Do not reuse them for any service other than integrating your own ORVIBO account.

### Development and verification

Run the protocol tests, which do not require a Home Assistant installation:

```powershell
python -m unittest discover -s tests -v
```

Main project structure:

```text
orvibo-cloud/
├── custom_components/orvibo_cloud/
│   ├── api.py               # REST login and device-table retrieval
│   ├── binary.py            # Mutual-TLS binary cloud protocol
│   ├── config_flow.py       # UI setup, device, and area selection
│   ├── coordinator.py       # Cloud state refresh
│   ├── cover.py             # Curtain entities
│   ├── light.py             # Light entities
│   ├── sensor.py            # Diagnostic sensors
│   └── translations/        # Localized UI strings
├── tests/
├── hacs.json
└── README.md
```

### Acknowledgements

Protocol behavior was cross-checked against packet captures and the MIT-licensed [`orvibo-homeassistant-curtains`](https://github.com/kjanko/orvibo-homeassistant-curtains) project.

---

## License

MIT
