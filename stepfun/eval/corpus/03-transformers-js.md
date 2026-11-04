# 在浏览器中运行 ONNX 模型

Transformers.js 把 Hugging Face 的 Transformers 接口搬到了浏览器，底层通过 ONNX Runtime Web 执行 ONNX 模型。安装 @huggingface/transformers 后，调用 pipeline('feature-extraction', modelId, options) 即可得到一个 embedding 管道，输入文本数组，输出每个文本的向量。

模型可以直接从公开模型仓库下载，也可以放在本地静态目录，通过 env.localModelPath 指向它，并用 env.allowRemoteModels=false 禁止远端访问。本地加载不会改变推理位置：计算仍然发生在用户设备的浏览器里。

为了减少首屏等待，应当把模型加载放在 Web Worker 中，避免阻塞主线程渲染；同时把权重文件放在同源静态路径并开启浏览器缓存。
