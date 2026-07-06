import { useState } from "react";
import "./App.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const handleFileChange = (event) => {
    const file = event.target.files[0];
    setSelectedFile(file);
    setResult(null);
    setErrorMsg("");

    if (file) {
      const localUrl = URL.createObjectURL(file);
      setPreviewUrl(localUrl);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setErrorMsg("请先选择一张图片。");
      return;
    }

    setLoading(true);
    setErrorMsg("");
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await fetch(`${API_BASE_URL}/predict`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`请求失败，状态码：${response.status}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (error) {
      setErrorMsg(error.message || "上传或推理失败。");
    } finally {
      setLoading(false);
    }
  };

  const getResultImageUrl = () => {
    if (result?.result_image_url) return result.result_image_url;
    if (!result?.result_url) return "";
    if (result.result_url.startsWith("http")) return result.result_url;
    if (result.result_url.startsWith(API_BASE_URL)) return result.result_url;
    return `${API_BASE_URL}${result.result_url}`;
  };

  const resultImageUrl = getResultImageUrl();

  const formatLabels = (labels = []) => {
    if (!labels.length) return "";
    const uniqueLabels = [...new Set(labels)];
    if (uniqueLabels.length === 1 && labels.length > 1) {
      return `${uniqueLabels[0]} × ${labels.length}`;
    }
    return labels.join(", ");
  };

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1>
            <span className="logo-mark">
              <img src="/tongji-logo.png" alt="Tongji University" />
            </span>
            MAMT2 Cloud SHM
          </h1>
          <p>结构表观病害检测与实例分割云原生平台</p>
        </div>
        <span className="badge">FastAPI + MAMT2 + K8s Ready</span>
      </header>

      <main className="main">
        <section className="panel upload-panel">
          <h2>图片上传</h2>

          <input
            className="file-input"
            type="file"
            accept="image/*"
            onChange={handleFileChange}
          />

          <button className="button" onClick={handleUpload} disabled={loading}>
            {loading ? "识别中..." : "开始识别"}
          </button>

          {errorMsg && <p className="error">{errorMsg}</p>}

          <div className="info-box">
            <p><strong>当前模型：</strong>MAMT2 / Mask R-CNN</p>
            <p><strong>输出内容：</strong>类别、置信度、bbox、mask、结果图</p>
          </div>
        </section>

        <section className="panel image-panel">
          <h2>原始图片</h2>
          {previewUrl ? (
            <img className="image" src={previewUrl} alt="input preview" />
          ) : (
            <div className="placeholder">请选择一张结构病害图片</div>
          )}
        </section>

        <section className="panel image-panel">
          <h2>识别结果</h2>
          {resultImageUrl ? (
            <img className="image" src={resultImageUrl} alt="prediction result" />
          ) : (
            <div className="placeholder">等待推理结果</div>
          )}
        </section>

        <section className="panel result-panel">
          <h2>结果信息</h2>

          {result ? (
            <div className="result-content">
              <div className="result-row">
                <span>状态</span>
                <strong>{result.status}</strong>
              </div>

              <div className="result-row">
                <span>输入文件</span>
                <strong>{result.input_filename}</strong>
              </div>

              <div className="result-row">
                <span>类别</span>
                <strong>{formatLabels(result.labels)}</strong>
              </div>

              <div className="result-row">
                <span>置信度</span>
                <strong>{result.scores?.map((s) => Number(s).toFixed(2)).join(", ")}</strong>
              </div>

              <details className="debug-details">
                <summary>查看原始推理结果 JSON</summary>
                <pre>{JSON.stringify(result, null, 2)}</pre>
              </details>
            </div>
          ) : (
            <div className="placeholder">暂无结果</div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;

