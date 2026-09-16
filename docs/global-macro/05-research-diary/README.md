# Global Macro Research Diary｜全球宏观研究日记

Global Macro Research Diary 是 Statistics Lab · Global Macro Lab 的日度研究输出。这里记录的是一个研究者如何根据当时能够获得的数据、政策信息和市场价格形成判断，以及哪些新证据会使判断改变。它不是新闻清单，也不以增加标题、表格或篇幅代替分析。

## 阅读入口

[Research Diary #001 · 2026年9月15日：油价、5%美债与Fed再定价：通胀问题并没有结束](Global-Macro-Research-Diary-2026-09-15.md)

本篇已在9月15日美股常规交易收盘后完成盘后更新，采用连续段落分析，并在正文脚注与文末 References & Sources 中对应列出27项来源。观察窗口截止于9月15日美股收盘及当日可获得的日终数据，仍严格早于9月16日FOMC决议，因此不是决议后的复盘。

## 正文写作约定

正文以完整段落为基本单位。一段分析应自然交代事实、经济机制、可能的另一种解释和阶段性判断，而不是把一个论点拆成多个单独句子。数据与机构观点嵌入论证，不单列机构名字充当证据。标题围绕当天真正需要解释的矛盾展开，允许合并章节，不强制套用固定数量的小节。

日记通常从市场变化进入，讨论增长、通胀、政策反应与金融条件，再比较机构分歧和跨资产影响，最后留下 Statistics Lab 的当前判断及修正条件。这个顺序是研究逻辑，不是需要逐项填空的模板。正文不强制加入 Executive Thesis、Macro Dashboard 或 Base/Bull/Bear 表格；未经估计或校准的概率，不包装成模型输出。

指标面板、数据字典和模型实现分别保存在[数据面板](../02-dashboard/README.md)与[数据研究本](../08-data-notebook/README.md)。日记负责把证据组织成可阅读的分析，不重复堆放其他模块的全部内容。

## 证据与引用约定

每个关键事实应注明统计期间、发布时点、单位及必要口径，正文引用对应具体来源。区分同比与环比折年、名义与实际、单月与累计、盘中与收盘、现货与期货、日频与周频。不同时间的报价可以用于观察，但不得伪装成同一时刻的数据面板；涉及相减、比较或分解时，先对齐日期、期限与口径。

官方发布优先用于经济数据。机构判断注明具体部门、作者、发布日期和预测期限；客户报告的媒体转述与公开原文分开标识。只读到摘要或无法核对付费正文时，明确说明范围，不补写未见原文的细节。长期研究框架不能冒充当天的新观点，记者报道不能冒充央行承诺，销售人员讨论不能自动代表整个机构的统一预测。

正文使用标准 Markdown 脚注，文末列出标题、日期、直接链接与使用范围，不写只有机构首页的笼统参考目录，不使用仅在聊天界面有效的引用标记。滚动网页注明观察版本；本篇的描述性计算注明输入数据和算法，未执行的模型不宣称已经估计。

## 判断与版本维护

结论应清楚表达目前更支持哪一种解释，同时说明证据不足之处和会改变判断的信号。事实、机构预测和 Statistics Lab 的推断分别表述。解释市场共同变化，不自动等于识别出了因果关系；情景分析也不等于已经测得情景概率。

历史日记保留原始观察日期，不把后来才公布的数据写成当时已知信息。事实订正或观点变化在文末记录修订原因。目录迁移先核对全文与内容哈希，再处理旧路径；不可用重新生成的摘要替代原文。日记正文与目录说明尽量在同一提交中更新，提交后重新读取默认分支确认内容。以 Git 历史保留版本，不另建多个并行的 daily 或 research-diary 目录。

## English summary

This journal records time-stamped macroeconomic observations and conditional research judgments in sustained prose. Evidence is linked to specific sources; data conventions, publication dates and market observation times are kept explicit. Institutional forecasts are distinguished from policy decisions and the author's own interpretation. Dashboards and model implementations belong in their dedicated modules. Revisions preserve the original information window and are recorded transparently.
