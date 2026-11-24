# 纸样修复批签台：运行契约

## 对象与决策

- 规则 ID 绑定一份不可改写的规则。藏品登记时保存该规则全文。藏品记录页宽高、标题和规则正文；区域保存目标纸面、纤维轴、厚度与 pH，以及在藏品页上的损坏轮廓。
- 批次提供共享停用状态；每张实物纸页持有自己的厚度、pH、纤维轴及双面色值，并带 `quota` 取纸笔数上限（缺省 512）。纸面标识 `front/back` 不生成第二套纸页坐标。已停用批次不能登记新纸页或启动新试补、补片、备料或开裁，既有裁切和观察可查；已启动的观察仍可录入，既有完工记录仍可封存；已经确认开裁的备料位在批次停用后仍可登记回执。
- 坐标为左上原点的整数毫米，宽高不超过 3000。轮廓由 4–32 个交替水平垂直顶点构成，不允许自触、自交及不同区域重叠。取纸矩形为 `[左,上,右,下]`，左和上含边界，面积重叠才冲突。每张纸页的试补与补片占位跨藏品、纸面和修订共享。
- 厚度以 μm 记，pH 和 Lab 各分量用十倍整数记。旋转 `90` 交换纤维轴及补片尺寸，`0` 不变；只对相同 `condition` 的选定面计算 Lab 欧氏距离平方，不对异条件作推测或自动转换。厂批标签不参与适配计算。
- 试补引用一张纸页、一面、一个角度和一个实际切取区。按规则列出的时点逐条观察；翘边或漂移超限立即不合格，其余情况要等最后一个时点才合格。编号跨该藏品各修订唯一。在同一区当前修订，只有合格试补才能派生补片；补片必须整块落在轮廓内且不重叠。
- 成组备料按当前修订逐块登记合格试补、源纸矩形 `cut` 与缺口内拟贴位置 `origin`；按试补纸面与角度摆放后，各块须整块落在当前未覆盖缺口内、彼此不重叠，也不与已贴补片或仍占位的其他备料位重叠。只有整组源纸都可用、且全组不超出每张实物纸页剩余取纸笔数时才一起接受，否则整体失败不留占位。同一实物纸页正反面共用坐标，普通取样、另裁补片与各工作单的备料都按面积重叠冲突。
- 取纸笔数按实物纸页计：每条未交回的 `cut` 占位（含未结算承诺、已开裁、已裁）占一笔；同一备料位由承诺转已裁时占位键不变，故始终只占一笔；未动刀交回与撤销会释放占位和笔数。备料位状态机为 `committed → started → cut/returned`，开裁前可 `cancelled`，所在缺口复开后未结算者置 `superseded` 并释放；已裁位永久占位。
- 动刀前逐块 `start_cut` 确认，此时原修订仍须可用、纸批仍须有效。开裁后逐块 `receive` 交回带唯一编号的回执：`cut=true` 确认按备料位置裁下并永久占位，`cut=false` 确认未动刀并释放。回执编号跨全库唯一；每个备料位只结算一次，重送同一份回执不重复结算，改动原回执或换编号再结算一律拒绝。即使之后复开或纸批停用，已开裁的料仍可登记回执。
- 凭已裁回执贴补（`prepatch`）须重新核对备料修订、试补资格、纸批与原定缺口位置，并沿用原定取纸矩形与拟贴位置；成功才增加覆盖并把该笔实际裁切实例关联到补片。一笔已裁回执只可登记一片补片；贴放失败或工作单后续中止（复开）都不撤销实裁。封存输入含备料组，复算逐位核对状态机、占位、笔数与回执，并把备料补片的回执与原取纸矩形写入清单和 CSV。
- 覆盖等于损坏区面积时才可完工。复开生成新修订，当前试补与覆盖从零开始；原有事件与实物消耗不撤销。封存是对当前现场版本的签出，不递增现场版本；只允许非空且全区完工的现场。其输入为本藏品各区当前修订、规则、所引用的纸页和试补及补片，不是全库库存备份。复算检查封存内几何、面向、试补判定、裁切占位和清单；现场写入另检查全库占位。

## HTTP 与交付

前缀 `/api/`，请求为 UTF-8 JSON。`422` 表示入参不符合业务契约，`404` 表示未找到，`409` 表示版本、占位或状态冲突。除预检外，写操作在 SQLite `BEGIN IMMEDIATE` 内完成判断、占位、写入和事件追加；抛错则事务回滚。读操作在单次读事务内取快照。

| 方法和路径（省略 `/api`） | 结果 |
| --- | --- |
| `GET /catalog` | 规则、藏品、批次、纸页 |
| `POST /rules`、`/documents`、`/lots`、`/sheets` | 按 ID 登记事实（样例提供完整结构） |
| `POST /retire` | 传 `id`、`reason` 停用批次 |
| `GET /sheets/{sheet}` | 该纸页、全局裁切占位与取纸笔数用量（`quota_used`、`quota_remaining`） |
| `GET /documents/{doc}` | 当前区域、覆盖、观察、备料组与封存摘要 |
| `POST /documents/{doc}/preview` | 传 `zone`、`selection:{sheet,face,turn}`，返回各维相容性，不写状态 |
| `POST /documents/{doc}/zone` | 传 `expected` 和 `data:{id,label,outline,stock,surface}` |
| `POST /documents/{doc}/{trial,observe,patch,prepatch,finish,reopen}` | 传 `expected`、`zone`、`data`，成功返回新现场版本 |
| `POST /documents/{doc}/{prepare,cancel,start_cut,receive}` | 成组备料动作，传 `expected`、`data`（不含 `zone`），成功返回新现场版本 |
| `GET /documents/{doc}/events` | 按现场版本读取结果证据 |
| `POST /documents/{doc}/releases` | 传 `expected` 签出当前版，重复签出摘要不变 |
| `GET /documents/{doc}/releases/{version}` | 检核过的规范 JSON，可加 `?download` 下载 |
| `GET /documents/{doc}/releases/{version}/replay` 或 `/csv` | 复算回执或裁切 CSV |
| `GET /documents/{doc}/compare/{old}/{new}` | 按损坏区和贴放矩形比对早晚版，返回前后证据 |

区域动作的 `data` 包含：`trial` 为 `id`、`selection`、`cut`；`observe` 为试补 `id` 和 `observation:{hour,drift,lifting,note}`；`patch` 为新片 `id`、`trial`、`cut`、`origin`；`finish` 传空对象；`reopen` 传 `reason`。备料动作的 `data`：`prepare` 为组 `id` 与 `slots:[{id,zone,trial,cut,origin}]`；`cancel` 为 `{group}`；`start_cut` 为 `{group,slot}`；`receive` 为 `{group,slot,receipt,cut}`；`prepatch` 为新片 `id`、`group`、`slot`、`trial`、`cut`、`origin`（仍随请求带 `zone`）。所有修改都用操作者看过的藏品现场版本，冲突需刷新并重新核对，不自动覆盖。

封存 JSON 按排序键、无空白的 UTF-8 JSON 对 `format`、`inputs`、`manifest` 计算 SHA-256（排除 `sha256` 自身）；读出时校验摘要并复算逐片清单。CSV 使用固定列和 LF，取纸与贴放矩形使用空格分隔整数。版差中目标矩形相同但来源或修订变化记为 `changed`，几何分别消失或新出现在 `removed`、`added` 中报告。
