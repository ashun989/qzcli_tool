# qzcli 开发者文档

## 1. 项目定位

`qzcli` 是一个面向启智平台的 Python CLI，目标不是完整封装所有平台能力，而是围绕“任务查看、任务跟踪、资源发现、空闲节点选择、工作空间运行态观察”提供高频操作入口。

这个仓库的实现有两个明显特点：

1. 它同时使用了官方 OpenAPI 和站内内部 API。
2. 它把一部分运行态信息缓存在本地，形成“远端查询 + 本地索引”的混合模型。

如果只看 `README.md`，会觉得这是一个“任务管理 CLI”；如果看代码实现，实际更准确的描述是：

- OpenAPI 负责任务详情、停止任务、创建任务、规格查询、Token 获取。
- 浏览器 Cookie 认证的内部 API 负责工作空间列表、任务列表、节点维度、任务维度、集群基础信息。
- 本地 JSON 文件负责保存认证状态、资源缓存和被追踪的任务列表。

## 2. 技术栈与运行方式

- 语言: Python 3.8+
- 依赖: `requests`, `rich`
- 打包方式: `setuptools`
- CLI 入口: `qzcli=qzcli.cli:main`

安装入口定义在 `setup.py`，核心包为 `qzcli/`。

## 3. 代码结构

### 3.1 模块划分

- `qzcli/cli.py`
  - 命令行参数解析。
  - 所有子命令的 orchestration。
  - 用户交互、缓存更新、跨 API 聚合逻辑。
- `qzcli/api.py`
  - 启智 API 客户端。
  - 封装 Bearer Token 认证的 OpenAPI。
  - 封装基于浏览器 Cookie 的内部 API。
  - 封装 CAS -> Keycloak -> 启智站点的登录跳转流程。
- `qzcli/config.py`
  - `~/.qzcli` 下配置和缓存文件的加载/保存。
  - 环境变量覆盖逻辑。
- `qzcli/store.py`
  - 本地任务记录存储。
  - `JobRecord` 数据模型。
- `qzcli/display.py`
  - Rich/纯文本双输出层。
  - 时间、状态、表格渲染。
- `qzcli/crypto.py`
  - CAS 登录密码加密逻辑。

### 3.2 入口命令

CLI 子命令定义集中在 `qzcli/cli.py` 的 `main()` 中，当前暴露的命令有：

- `init`
- `list` / `ls`
- `status` / `st`
- `stop`
- `watch` / `w`
- `track`
- `import`
- `remove` / `rm`
- `clear`
- `cookie`
- `login`
- `workspace` / `ws`
- `workspaces` / `lsws` / `res` / `resources`
- `avail` / `av`
- `usage`

## 4. 两套认证模型

### 4.1 OpenAPI Token 认证

用于官方 OpenAPI。

流程：

1. 从环境变量或 `~/.qzcli/config.json` 读取用户名密码。
2. 调用 `POST /auth/token` 获取 `access_token`。
3. 将 token 缓存到 `~/.qzcli/.token_cache`。
4. 后续对 `/openapi/v1/...` 请求在 `Authorization: Bearer <token>` 中携带。

相关实现：

- `QzAPI._get_token()`
- `QzAPI._request()`

环境变量：

- `QZCLI_USERNAME`
- `QZCLI_PASSWORD`
- `QZCLI_API_URL`

### 4.2 浏览器 Cookie 认证

用于站内内部接口，主要服务于资源发现和运行态观察。

来源有两种：

1. 手工执行 `qzcli cookie`，把浏览器 cookie 写入本地。
2. 执行 `qzcli login`，自动走 CAS 登录流程拿到站点 session cookie。

Cookie 保存在 `~/.qzcli/.cookie`，其中还可以附带默认 `workspace_id`。

## 5. 本地状态与缓存

默认目录为 `~/.qzcli`。

文件清单：

- `config.json`
  - 基础配置、用户名密码、API 基地址。
- `.token_cache`
  - Bearer Token 与过期时间。
- `.cookie`
  - 浏览器 Cookie 与默认工作空间。
- `resources.json`
  - 工作空间资源缓存。
  - 包含项目、计算组、规格、更新时间。
- `jobs.json`
  - 本地追踪的任务列表。

### 5.1 资源缓存模型

`resources.json` 以工作空间为 key，缓存：

- `projects`
- `compute_groups`
- `specs`
- `updated_at`

这个缓存是 `res`、`avail`、`ls -c --all-ws` 等命令的前置依赖之一。

### 5.2 任务存储模型

`JobRecord` 是本地任务状态的核心结构，除了基础字段，还保存：

- `running_time_ms`
- `priority_level`
- `gpu_count`
- `instance_count`
- `compute_group_name`
- `gpu_type`
- `project_name`
- `url`

本地 store 的用途主要是：

- 跟踪外部脚本创建的任务 ID。
- 轮询刷新任务状态。
- 输出更友好的本地视图。

## 6. 主要命令的实现逻辑

### 6.1 任务相关

- `status`, `watch`, `track`, `import --refresh`, 本地 `list`
  - 都依赖 OpenAPI `train_job/detail`。
- `stop`
  - 依赖 OpenAPI `train_job/stop`。
- `list -c`
  - 依赖内部接口 `/api/v1/train_job/list`。

这里的设计是：

- “任务详情/停止”走官方接口。
- “任务列表”优先走内部接口，因为它能按工作空间拉取更多上下文。

### 6.2 资源发现

`res -u` 的核心流程：

1. 用 Cookie 调 `/api/v1/project/list` 发现可访问工作空间。
2. 对每个工作空间调 `/api/v1/train_job/list` 抽取项目、计算组、规格。
3. 再调 `/api/v1/cluster_metric/cluster_basic_info` 补充完整计算组列表。
4. 落地到 `resources.json`。

如果某工作空间历史任务为空，还会退化为：

- `/api/v1/cluster_metric/list_task_dimension`
- `/api/v1/cluster_metric/list_node_dimension`

来补项目和计算组信息。

### 6.3 空闲资源选择

`avail` 是这个仓库最有价值的业务逻辑之一：

1. 从 `resources.json` 获取工作空间和计算组范围。
2. 调 `/api/v1/cluster_metric/list_node_dimension` 拉节点维度数据。
3. 计算：
   - 空节点数
   - 空闲 GPU 总量
   - GPU 利用率
   - 各 GPU 空闲分布
4. 在 `--lp` 模式下，再通过 `/api/v1/cluster_metric/list_task_dimension` 估算低优任务占用，推断“可抢占空余”。

### 6.4 工作空间视图

`ws` 使用 `/api/v1/workspace/list_task_dimension` 查看工作空间运行中任务，并输出 GPU/CPU/MEM 使用率。

这个命令本质上不是 OpenAPI 能力，而是站内运营视图的 CLI 化。

### 6.5 使用率统计

`usage` 基于 `/api/v1/cluster_metric/list_task_dimension` 统计：

- GPU 卡数分布
- 用户维度分布
- 项目维度分布
- 任务类型分布
- 优先级分布

## 7. API 版图

### 7.1 已使用的官方 OpenAPI

| 能力 | 接口 |
| --- | --- |
| 获取 Token | `POST /auth/token` |
| 创建训练任务 | `POST /openapi/v1/train_job/create` |
| 查询任务详情 | `POST /openapi/v1/train_job/detail` |
| 停止任务 | `POST /openapi/v1/train_job/stop` |
| 查询规格列表 | `POST /openapi/v1/specs/list` |

### 7.2 已使用的内部 API

| 能力 | 接口 |
| --- | --- |
| 工作空间任务视图 | `POST /api/v1/workspace/list_task_dimension` |
| 训练任务列表 | `POST /api/v1/train_job/list` |
| 节点维度资源信息 | `POST /api/v1/cluster_metric/list_node_dimension` |
| 任务维度资源信息 | `POST /api/v1/cluster_metric/list_task_dimension` |
| 工作空间集群基础信息 | `POST /api/v1/cluster_metric/cluster_basic_info` |
| 项目列表/工作空间发现 | `POST /api/v1/project/list` |

## 8. 与 PDF《启智 分布式训练 OpenAPI 文档》的一致性评估

### 8.1 PDF 实际覆盖范围

从 PDF 提取到的内容看，这份文档一共 7 页，只覆盖了以下能力：

- `POST /auth/token`
- `POST /openapi/v1/train_job/create`
- `POST /openapi/v1/train_job/detail`
- `POST /openapi/v1/train_job/stop`

也就是说，这份 PDF 是“分布式训练 OpenAPI 子集文档”，不是“qzcli 所依赖全部接口文档”。

### 8.2 一致项

以下能力与 PDF 基本一致：

1. Token 获取
   - 代码通过 `POST /auth/token` 获取 token。
   - 也按 PDF 中的 `access_token`、`expires_in` 结构进行解析。
2. 训练任务详情
   - 代码调用 `POST /openapi/v1/train_job/detail`。
   - 请求参数为 `job_id`，与 PDF 一致。
3. 停止训练任务
   - 代码调用 `POST /openapi/v1/train_job/stop`。
   - 请求参数为 `job_id`，与 PDF 一致。
4. 创建训练任务
   - `QzAPI.create_job()` 调用 `POST /openapi/v1/train_job/create`。
   - 当前实现是“透传 config”，没有在客户端层面篡改字段结构，因此与文档契约并不冲突。

### 8.3 部分一致项

1. `framework_config` / `framewrok_config`
   - PDF 参数表中出现了 `framewrok_config` 的拼写。
   - 但 PDF 示例里使用的是 `framework_config`。
   - 代码内部也统一按 `framework_config` 处理。
   - 结论：更像是 PDF 参数表笔误，代码与示例保持一致。

2. `spec_id` 与 `quota_id`
   - PDF 在创建任务处要求传 `spec_id`，并说明可通过 detail 接口返回中的 `quota_id` 推断。
   - 代码在抽取规格缓存时，确实从 `detail/list` 返回结构中的 `instance_spec_price_info.quota_id` 读取规格 ID。
   - 结论：实现逻辑与 PDF 说明能对上。

### 8.4 超出 PDF 的实现

以下功能是项目实际依赖、但 PDF 没覆盖的：

1. 浏览器 Cookie 登录与 CAS 自动化。
2. 工作空间列表发现。
3. 工作空间维度任务概览。
4. 节点维度/任务维度资源统计。
5. 训练任务列表拉取。
6. 集群基础信息查询。
7. `/openapi/v1/specs/list` 的规格查询。

这意味着：

- 如果把 PDF 当成“官方 OpenAPI 文档”，那么项目对其“子集能力”是基本一致的。
- 如果把 PDF 当成“本项目接口依据的完整文档”，那么一致性明显不够，因为项目大量核心功能依赖 PDF 未披露的内部接口。

### 8.5 综合结论

建议把一致性结论分成两层来理解：

1. 对官方分布式训练 OpenAPI 子集来说
   - 一致性较高。
   - 核心的 `token/detail/stop/create` 均对得上。
2. 对整个 qzcli 项目来说
   - 一致性只有“部分一致”。
   - 原因不是实现偏离 PDF，而是项目能力范围远大于 PDF 覆盖范围。

一句话总结：

> `qzcli` 并不是“只围绕 PDF OpenAPI 构建的 CLI”，而是“在官方 OpenAPI 之上，进一步封装了启智站内私有接口”的 CLI。

## 9. 当前实现中的开发风险

以下问题不是 PDF 一致性问题，但在继续开发前值得注意：

1. `QzAPI.create_job()` 已实现，但 CLI 没有提供对应子命令。
   - 当前仓库“具备创建任务底层能力”，但“没有创建任务的用户入口”。
2. `QzAPI.list_specs()` 已实现，但当前 CLI 也没有暴露对应命令。
3. `workspace --sync` 分支看起来存在方法名不一致风险。
   - `cmd_workspace()` 调用了 `store.get_job()` 和 `store.add_job()`。
   - `JobStore` 当前实际暴露的方法是 `get()` 和 `add()`。
   - 如果执行 `qzcli ws --sync`，这一分支大概率会报错。
4. `cmd_cookie()` 中“测试 cookie 是否有效”的注释写的是 `/openapi/v1/train_job/list`。
   - 实际调用的是内部接口 `/api/v1/train_job/list`。
   - 这是注释与实现不一致，不影响运行，但会误导后续维护者。

## 10. 建议的后续演进方向

如果这个项目要继续工程化，建议优先做这几件事：

1. 明确分层
   - 把“官方 OpenAPI 客户端”和“内部站点 API 客户端”拆开。
2. 抽象认证
   - 把 Bearer Token 与 Cookie session 的生命周期管理拆成独立模块。
3. 补齐命令能力
   - 暴露 `create`、`specs` 等已经具备底层实现的功能。
4. 增加测试
   - 至少补充 `JobStore`、参数解析、资源提取、状态格式化的单元测试。
5. 给内部 API 打标签
   - 在文档和代码中明确标注哪些能力依赖非公开接口，降低维护误判。

## 11. 开发结论

从开发者角度看，这个仓库已经形成了一个可用的“启智运维型 CLI”雏形，但它的真实依赖面比 PDF 所示的大很多。

因此最重要的结论不是“代码是否遵循 PDF”，而是：

- 项目对 PDF 覆盖的 OpenAPI 基本遵循。
- 项目核心价值主要建立在 PDF 之外的内部接口之上。
- 后续若平台内部接口变动，项目的脆弱点不在 `detail/stop/create`，而在 `workspace/train_job list/cluster_metric/project list` 这一整组私有接口。
