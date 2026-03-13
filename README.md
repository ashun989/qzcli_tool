# qzcli - 启智平台任务管理 CLI

一个类似 kubectl/docker 风格的 CLI 工具，用于管理启智平台任务。

## 特性

- **一键登录**: `qzcli login` 通过 CAS 认证自动获取 cookie，无需手动复制
- **全局代理**: `qzcli proxy` 支持为所有请求配置 `https` / `socks5` 代理
- **资源发现**: `qzcli res -u` 自动发现工作空间、计算组、规格等资源并本地缓存
- **节点查询**: `qzcli avail` 查询各计算组空余节点，支持低优任务统计
- **任务列表**: 美观的卡片式显示，完整 URL 方便点击
- **状态监控**: watch 模式实时跟踪任务进度

开启启智的极致hack
```bash
qzcli login -u 用户名 -p 密码 && qzcli avail
 
```
```
分布式
  计算组                          空节点     总节点     空GPU GPU类型     
  -----------------------------------------------------------------
  某gpu2-3号机房-2                    3      xxx  x/xxx 某gpu2      
  某gpu2-3号机房                      0      xxx   x/xxx 某gpu2      
  某gpu2-2号机房                      0      xxx   x/xxx 某gpu2      
  cuda12.8版本某gpu1                 0      xxx  x/xxx 某gpu1   
```

## 安装依赖

```bash
pip install rich requests PySocks
```

## 快速开始

```bash
# 1. 登录（自动获取 cookie）
qzcli login

# 2. 如需代理，先设置全局代理
# qzcli proxy https://127.0.0.1:7890

# 3. 更新资源缓存（首次使用必须执行，自动发现所有可访问的工作空间）
qzcli res -u

# 4. 查看空余节点
qzcli avail

# 5. 查看运行中的任务
qzcli ls -c -r

# 6. 查询某个计算组的可用规格
qzcli specs -w CI -g H200
```

> **重要**: 
> - 首次使用必须执行 `qzcli res -u`，会自动发现并缓存所有你有权限访问的工作空间
> - 如果遇到 `未找到名称为 'xxx' 的工作空间` 错误，说明缓存需要更新，请重新执行 `qzcli res -u`
> - 新加入的工作空间/项目需要重新执行 `qzcli res -u` 来更新缓存

## 推荐工作流

### 每日使用

```bash
# 登录并查看资源
qzcli login && qzcli avail

# 输出示例：
# CI-情景智能
#   计算组                          空节点    总节点 GPU类型     
#   -----------------------------------------------------
#   OV3蒸馏训练组                       4      xxx 某gpu2      
#   openveo训练组                     1     xxx 某gpu2      
#   ...
# 分布式
#   某gpu2-2号机房                      1    xxx 某gpu2      
```

### 提交任务前

```bash
# 找有 4 个空闲节点的计算组
qzcli avail -n 4 -e

# 如果需要考虑低优任务占用的节点（较慢，但更准确地反映潜在可用资源）
qzcli avail --lp -n 4

# 如果开启了 --lp (low priority) 模式，建议配合 -w 指定工作空间以加快速度
qzcli avail --lp -w CI -n 4
```

### 查看任务

```bash
# 查看所有工作空间运行中的任务
qzcli ls -c --all-ws -r

# 查看指定工作空间
qzcli ls -c -w CI -r
```

## 命令参考

### 认证命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `login` | CAS 登录获取 cookie | `qzcli login` |
| `proxy` | 设置全局代理 | `qzcli proxy socks5://127.0.0.1:1080` |
| `cookie` | 手动设置 cookie | `qzcli cookie -f cookies.txt` |

```bash
# 交互式登录
qzcli login

# 带参数登录
qzcli login -u 学工号 -p 密码

# 如果之前成功执行过 qzcli login，后续也可以直接复用它保存的登录认证信息
qzcli login

# 设置全局 HTTPS 代理
qzcli proxy https://127.0.0.1:7890

# 设置全局 SOCKS5 代理
qzcli proxy socks5://127.0.0.1:1080

# 查看当前代理
qzcli proxy --show

# 测试代理连通性
qzcli proxy --test

# 清除代理
qzcli proxy --clear

# 查看当前 cookie
qzcli cookie --show

# 清除 cookie
qzcli cookie --clear
```

### 资源管理

| 命令 | 别名 | 说明 |
|------|------|------|
| `resources` | `res`, `lsws` | 管理工作空间资源缓存 |
| `avail` | `av` | 查询计算组空余节点 |

```bash
# 列出已缓存的工作空间
qzcli res --list

# 更新所有工作空间的资源缓存
qzcli res -u

# 更新指定工作空间
qzcli res -w CI -u

# 给工作空间设置别名
qzcli res -w ws-xxx --name 我的空间

# 查看空余节点（默认不包含低优任务统计，速度较快）
qzcli avail

# 查看空余节点（包含低优任务统计，即：空节点 + 低优任务占用的节点）
qzcli avail --lp

# 只查看 CI 工作空间
qzcli avail -w CI

# 显示空闲节点名称
qzcli avail -w CI -v

# 找满足 N 节点需求的计算组
qzcli avail -n 4

# 导出为脚本可用格式
qzcli avail -n 4 -e
```

### 任务列表

| 命令 | 别名 | 说明 |
|------|------|------|
| `list` | `ls` | 列出任务 |

```bash
# Cookie 模式（从 API 获取）
qzcli ls -c -w CI           # 指定工作空间
qzcli ls -c --all-ws        # 所有工作空间
qzcli ls -c --all-ws --track  # 同步所有工作空间任务到本地追踪列表
qzcli ls -c -w CI -r        # 只看运行中
qzcli ls -c -w CI -n 50     # 显示 50 条

# 本地模式（从本地存储）
qzcli ls                    # 默认列表
qzcli ls -r                 # 运行中
qzcli ls --no-refresh       # 不刷新状态
```

### 任务管理

| 命令 | 说明 | 示例 |
|------|------|------|
| `status` | 查看任务详情 | `qzcli status job-xxx` |
| `stop` | 停止任务 | `qzcli stop job-xxx` |
| `watch` | 实时监控 | `qzcli watch -i 10` |
| `track` | 追踪单个任务 | `qzcli track job-xxx` |
| `create` | 从 JSON 文件创建任务 | `qzcli create -f job.json` |
| `specs` | 查询计算组可用规格 | `qzcli specs -w CI -g H200` |

```bash
# 从 JSON 文件创建训练任务
qzcli create -f job.json

# 创建后显示原始 API 响应
qzcli create -f job.json --json

# 查询某个工作空间计算组的规格
qzcli specs -w CI -g H200

# 输出规格原始 JSON
qzcli specs -w CI -g H200 --json

# 一键把当前可见的所有工作空间任务同步到本地 jobs.json
qzcli ls -c --all-ws --track
```

创建任务的 JSON 文件示意：

```json
{
  "name": "demo-job",
  "logic_compute_group_id": "lcg-xxxx",
  "project_id": "project-xxxx",
  "framework": "pytorch",
  "command": "python train.py",
  "task_priority": 4,
  "workspace_id": "ws-xxxx",
  "framework_config": [
    {
      "image": "docker.sii.shaipower.online/inspire-studio/pytorch:25.06-py3",
      "image_type": "SOURCE_OFFICIAL",
      "instance_count": 1,
      "shm_gi": 0,
      "spec_id": "spec-xxxx"
    }
  ]
}
```

### 工作空间视图

```bash
# 查看工作空间内运行任务（含 GPU 使用率）
qzcli ws

# 查看所有项目
qzcli ws -a

# 过滤指定项目
qzcli ws -p "长视频"
```

## 输出示例

### qzcli avail -v

```
CI-情景智能
  计算组                          空节点    总节点 GPU类型     
  -----------------------------------------------------
  OV3蒸馏训练组                       4      8 某gpu2      
    空闲: qb-prod-gpu1006, qb-prod-gpu1029, qb-prod-gpu1034, qb-prod-gpu1064
  openveo训练组                     1     79 某gpu2      
    空闲: qb-prod-gpu2000
```

### qzcli ls -c -w CI -r

```
工作空间: CI-情景智能

[1] ● 运行中 | 44分钟前 | 44分36秒
    eval-OpenVeo3-I2VA-A14B-1227-8s...
    8×某gpu2 | 4节点 | GPU资源组
    https://qz.sii.edu.cn/jobs/distributedTrainingDetail/job-xxx

[2] ● 运行中 | 58分钟前 | 56分47秒
    sglang-eval-A14B-360p-wsd-105000...
    8×某gpu2 | 2节点 | GPU资源组
```

## 配置文件

配置存储在 `~/.qzcli/` 目录：

| 文件 | 说明 |
|------|------|
| `config.json` | OpenAPI 认证信息、login 独立保存的用户名密码、全局代理 |
| `jobs.json` | 本地任务历史 |
| `.cookie` | Cookie（login 命令自动管理） |
| `resources.json` | 资源缓存（工作空间、计算组等） |

## 环境变量

```bash
export QZCLI_USERNAME="your_username"
export QZCLI_PASSWORD="your_password"
export QZCLI_API_URL="https://qz.sii.edu.cn"
export QZCLI_PROXY_URL="socks5://127.0.0.1:1080"
```

## 代理配置

如果当前网络不能直接访问 `*.sii.edu.cn`，可以设置全局代理。代理会覆盖：

- OpenAPI 请求
- 内部 `/api/v1/*` 请求
- `qzcli login` 的 CAS / Keycloak / 启智站点登录流程

支持的格式只有：

- `https://host:port`
- `socks5://host:port`

其中 `socks5://` 在实际请求时会按 `socks5h://` 方式处理，由代理端完成 DNS 解析，避免本地 DNS 影响访问 `*.sii.edu.cn`。

示例：

```bash
qzcli proxy https://127.0.0.1:7890
qzcli proxy --show
qzcli proxy --test
```

## 使用建议

- **日常使用**: `qzcli login && qzcli avail` 一键登录并查看资源
- **提交前**: `qzcli avail -n 4 -e` 找合适的计算组并导出配置
- **批量追踪**: `qzcli ls -c --all-ws --track` 把当前可见任务同步到本地追踪列表
- **监控任务**: `qzcli ls -c --all-ws -r` 查看所有工作空间运行中的任务
- **详细信息**: `qzcli ws` 查看 GPU/CPU/内存使用率
