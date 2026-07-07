"use client";

import { useState, useRef, useEffect } from "react";

export default function ImageRescaler() {
  const [mode, setMode] = useState<"template" | "process">("template");
  const [templates, setTemplates] = useState<string[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string>("default");
  const [templateName, setTemplateName] = useState<string>("");

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>("");
  const [templatePreview, setTemplatePreview] = useState<string>("");
  const [processedImage, setProcessedImage] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch("http://localhost:5000/cleanup", { method: "POST" }).catch((err) =>
      console.error("Cleanup failed:", err),
    );
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const response = await fetch("http://localhost:5000/list-templates");
      const data = await response.json();
      setTemplates(data.templates || []);
      if (data.templates.length > 0) {
        setSelectedTemplate(data.templates[0]);
        loadTemplatePreview(data.templates[0]);
      }
    } catch (err) {
      console.error("Failed to load templates:", err);
    }
  };

  const loadTemplatePreview = async (templateName: string) => {
    try {
      const response = await fetch(
        `http://localhost:5000/get-template/${templateName}`,
      );
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      setTemplatePreview(url);
    } catch (err) {
      console.error("Failed to load template:", err);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setProcessedImage("");
      setError("");

      const reader = new FileReader();
      reader.onloadend = () => {
        setPreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleCreateTemplate = async () => {
    if (!selectedFile || !templateName.trim()) {
      setError("Please provide both an image and a template name");
      return;
    }

    setLoading(true);
    setError("");

    const formData = new FormData();
    formData.append("image", selectedFile);
    formData.append("template_name", templateName.trim());

    try {
      const response = await fetch("http://localhost:5000/create-template", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Template creation failed");
      }

      alert(`Template "${templateName}" created successfully!`);
      setTemplateName("");
      handleReset();
      loadTemplates();
      setMode("process");
    } catch (err: any) {
      setError(err.message || "Failed to create template");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleProcess = async () => {
    if (!selectedFile) {
      setError("Please select an image first");
      return;
    }

    if (!selectedTemplate) {
      setError("Please create a template first");
      return;
    }

    setLoading(true);
    setError("");

    const formData = new FormData();
    formData.append("image", selectedFile);
    formData.append("template_name", selectedTemplate);

    try {
      const response = await fetch("http://localhost:5000/process", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || "Processing failed");
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      setProcessedImage(url);

      const contentDisposition = response.headers.get("Content-Disposition");
      const filenameMatch = contentDisposition?.match(
        /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/,
      );
      const filename =
        filenameMatch?.[1]?.replace(/['"]/g, "") || `image_${Date.now()}.png`;

      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (err: any) {
      setError(err.message || "Failed to process image");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setPreview("");
    setProcessedImage("");
    setError("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <div className="min-h-screen bg-black text-white">
      <div className="max-w-3xl mx-auto px-6 py-16 sm:py-24">
        {/* Header */}
        <div className="text-center mb-16">
          <h1 className="text-5xl sm:text-6xl font-semibold tracking-tight mb-4">
            Product Image Rescaler
          </h1>
          <p className="text-lg text-gray-400">
            Trace a reference product once. Every other image is traced and
            scale-matched to it, output as a clean 500×500 image.
          </p>
        </div>

        {/* Tab Navigation */}
        <div className="flex justify-center gap-8 mb-12">
          <button
            onClick={() => setMode("template")}
            className={`pb-1 text-sm transition-all cursor-pointer ${
              mode === "template"
                ? "text-white border-b-2 border-white"
                : "text-gray-500 hover:text-gray-300 border-b-2 border-transparent"
            }`}
          >
            Create Template
          </button>
          <button
            onClick={() => setMode("process")}
            className={`pb-1 text-sm transition-all cursor-pointer ${
              mode === "process"
                ? "text-white border-b-2 border-white"
                : "text-gray-500 hover:text-gray-300 border-b-2 border-transparent"
            }`}
          >
            Rescale Image
          </button>
        </div>

        {/* Main Content Area */}
        <div className="mb-20">
          {mode === "template" ? (
            <>
              {/* Template Mode */}
              <div className="text-center mb-10">
                <h2 className="text-2xl font-semibold mb-3">Create Template</h2>
                <p className="text-gray-400">
                  Upload a reference product photo. The real product is traced
                  out (background ignored) and its size/position becomes the
                  target for every image matched against it.
                </p>
              </div>

              <div className="bg-linear-to-b from-zinc-900/50 to-zinc-900/20 rounded-2xl border border-zinc-800 p-8">
                <div className="space-y-8">
                  <div>
                    <label
                      htmlFor="template-name"
                      className="block text-sm mb-3"
                    >
                      Template Name
                    </label>
                    <input
                      id="template-name"
                      name="templateName"
                      type="text"
                      value={templateName}
                      onChange={(e) => setTemplateName(e.target.value)}
                      placeholder="e.g., Product Standard"
                      className="w-full px-4 py-3 bg-black/50 border border-zinc-800 rounded-lg focus:outline-none focus:ring-2 focus:ring-white/20 focus:border-transparent transition-all placeholder:text-gray-600 cursor-text"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="template-image"
                      className="block text-sm mb-3"
                    >
                      Reference Image
                    </label>
                    <input
                      id="template-image"
                      name="templateImage"
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      onChange={handleFileSelect}
                      className="block w-full text-sm text-gray-400 file:mr-4 file:py-3 file:px-4 file:rounded-lg file:border file:border-zinc-800 file:text-sm file:font-medium file:bg-white file:text-black hover:file:bg-gray-100 file:cursor-pointer cursor-pointer file:transition-all"
                    />
                  </div>
                </div>

                <div className="flex gap-3 mt-8">
                  <button
                    onClick={handleCreateTemplate}
                    disabled={!selectedFile || !templateName.trim() || loading}
                    className="flex-1 h-11 px-6 bg-white text-black text-sm rounded-lg hover:bg-gray-100 disabled:bg-zinc-800 disabled:text-zinc-600 disabled:cursor-not-allowed transition-all cursor-pointer"
                  >
                    {loading ? "Tracing..." : "Create Template"}
                  </button>
                  <button
                    onClick={handleReset}
                    className="h-11 px-6 bg-transparent border border-zinc-700 text-sm rounded-lg hover:bg-zinc-800 hover:border-zinc-600 transition-all cursor-pointer"
                  >
                    Reset
                  </button>
                </div>
              </div>
            </>
          ) : (
            <>
              {/* Process Mode */}
              <div className="text-center mb-10">
                <h2 className="text-2xl font-semibold mb-3">Rescale Image</h2>
                <p className="text-gray-400">
                  Upload any product photo. It's traced, scale-matched to the
                  template 1:1, and output as a clean 500×500 image.
                </p>
              </div>

              <div className="bg-linear-to-b from-zinc-900/50 to-zinc-900/20 rounded-2xl border border-zinc-800 p-8">
                <div className="space-y-8">
                  <div className="relative">
                    <label
                      htmlFor="select-template"
                      className="block text-sm mb-3"
                    >
                      Select Template
                    </label>
                    <select
                      id="select-template"
                      name="selectedTemplate"
                      value={selectedTemplate}
                      onChange={(e) => {
                        setSelectedTemplate(e.target.value);
                        loadTemplatePreview(e.target.value);
                      }}
                      className="w-full px-4 py-3 bg-black/50 border border-zinc-800 rounded-lg focus:outline-none focus:ring-2 focus:ring-white/20 focus:border-transparent transition-all cursor-pointer appearance-none pr-10"
                    >
                      {templates.length === 0 && (
                        <option value="">No templates available</option>
                      )}
                      {templates.map((template) => (
                        <option key={template} value={template}>
                          {template}
                        </option>
                      ))}
                    </select>
                    <svg
                      className="absolute right-3 top-11.5 w-5 h-5 text-gray-400 pointer-events-none"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 9l-7 7-7-7"
                      />
                    </svg>
                  </div>

                  <div>
                    <label
                      htmlFor="product-image"
                      className="block text-sm mb-3"
                    >
                      Product Image
                    </label>
                    <input
                      id="product-image"
                      name="productImage"
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      onChange={handleFileSelect}
                      className="block w-full text-sm text-gray-400 file:mr-4 file:py-3 file:px-4 file:rounded-lg file:border file:border-zinc-800 file:text-sm file:font-medium file:bg-white file:text-black hover:file:bg-gray-100 file:cursor-pointer cursor-pointer file:transition-all"
                    />
                  </div>
                </div>

                <div className="flex gap-3 mt-8">
                  <button
                    onClick={handleProcess}
                    disabled={!selectedFile || !selectedTemplate || loading}
                    className="flex-1 h-11 px-6 bg-white text-black text-sm rounded-lg hover:bg-gray-100 disabled:bg-zinc-800 disabled:text-zinc-600 disabled:cursor-not-allowed transition-all cursor-pointer"
                  >
                    {loading ? "Tracing & Rescaling..." : "Rescale Image"}
                  </button>
                  <button
                    onClick={handleReset}
                    className="h-11 px-6 bg-transparent border border-zinc-700 text-sm rounded-lg hover:bg-zinc-800 hover:border-zinc-600 transition-all cursor-pointer"
                  >
                    Reset
                  </button>
                </div>
              </div>
            </>
          )}

          {/* Error Message */}
          {error && (
            <div className="mt-8 p-4 border border-red-900/50 bg-red-950/30 rounded-xl">
              <p className="text-sm text-red-400 text-center">{error}</p>
            </div>
          )}
        </div>

        {/* Image Preview Grid */}
        <div className="grid md:grid-cols-3 gap-6 max-w-4xl mx-auto">
          {mode === "process" && templatePreview && (
            <div className="border border-zinc-800 rounded-xl p-5 bg-linear-to-b from-zinc-900/30 to-transparent">
              <h3 className="text-xs font-semibold text-gray-500 mb-4 uppercase tracking-wider">
                Template (traced)
              </h3>
              <div className="relative aspect-square bg-zinc-950 rounded-lg overflow-hidden border border-zinc-900">
                <img
                  src={templatePreview}
                  alt="Template"
                  className="w-full h-full object-contain p-3"
                />
              </div>
            </div>
          )}

          {preview && (
            <div className="border border-zinc-800 rounded-xl p-5 bg-linear-to-b from-zinc-900/30 to-transparent">
              <h3 className="text-xs font-semibold text-gray-500 mb-4 uppercase tracking-wider">
                {mode === "template" ? "Reference" : "Upload"}
              </h3>
              <div className="relative aspect-square bg-zinc-950 rounded-lg overflow-hidden border border-zinc-900">
                <img
                  src={preview}
                  alt="Uploaded"
                  className="w-full h-full object-contain p-3"
                />
              </div>
            </div>
          )}

          {processedImage && (
            <div className="border border-zinc-800 rounded-xl p-5 bg-linear-to-b from-zinc-900/30 to-transparent">
              <h3 className="text-xs font-semibold text-gray-500 mb-4 uppercase tracking-wider">
                Result (500×500)
              </h3>
              <div className="relative aspect-square bg-zinc-950 rounded-lg overflow-hidden border border-zinc-900">
                <img
                  src={processedImage}
                  alt="Processed"
                  className="w-full h-full object-contain p-3"
                />
              </div>
              <p className="mt-4 text-xs text-gray-600 text-center">
                Downloaded automatically
              </p>
            </div>
          )}
        </div>

        {/* How It Works Section */}
        <div className="mt-24 pt-16 border-t border-zinc-800">
          <h3 className="text-2xl font-semibold mb-12 text-center">
            How it works
          </h3>
          <div className="grid md:grid-cols-2 gap-16 max-w-3xl mx-auto">
            <div>
              <div className="flex items-start gap-5">
                <div className="shrink-0 w-10 h-10 bg-white text-black rounded-full flex items-center justify-center text-base font-semibold">
                  1
                </div>
                <div>
                  <h4 className="font-semibold mb-4 text-lg">
                    Create Template
                  </h4>
                  <ul className="space-y-3 text-gray-400 leading-relaxed">
                    <li className="flex items-start gap-3">
                      <span className="text-gray-600 mt-1">•</span>
                      <span>Upload a reference product photo</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="text-gray-600 mt-1">•</span>
                      <span>System traces the real product only</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="text-gray-600 mt-1">•</span>
                      <span>Stores its size and position as the target</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
            <div>
              <div className="flex items-start gap-5">
                <div className="shrink-0 w-10 h-10 bg-white text-black rounded-full flex items-center justify-center text-base font-semibold">
                  2
                </div>
                <div>
                  <h4 className="font-semibold mb-4 text-lg">Rescale Image</h4>
                  <ul className="space-y-3 text-gray-400 leading-relaxed">
                    <li className="flex items-start gap-3">
                      <span className="text-gray-600 mt-1">•</span>
                      <span>Upload any product photo</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="text-gray-600 mt-1">•</span>
                      <span>Traces and matches the template's scale 1:1</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="text-gray-600 mt-1">•</span>
                      <span>White-filled, output at clean 500×500px</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
