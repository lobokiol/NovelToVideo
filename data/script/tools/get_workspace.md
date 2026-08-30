# 工具：get_workspace

## 用途

读取三个创作阶段工作区的当前完整内容，了解已有创作进度与上下文。

## 参数

无参数。

## 返回

- `activeTab`：当前活动选项卡（skeleton / strategy / script）；
- `skeleton`：故事骨架工作区全文（Markdown）；
- `strategy`：改编策略工作区全文（Markdown）；
- `script`：剧本草案工作区全文（Markdown）。

## 使用时机

回答涉及已有故事骨架、改编策略或剧本草案内容的问题前调用；系统提示词中的工作区内容被截断时，通过本工具读取完整正文。