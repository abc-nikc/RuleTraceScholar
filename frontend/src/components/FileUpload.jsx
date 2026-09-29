import { useState, useRef } from 'react';
import { Upload, FileText, Loader2, BookOpenCheck, Route, FlaskConical } from 'lucide-react';
import { uploadFiles } from '../api';

export default function FileUpload({ onUploaded, onAnalyze, disabled }) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState([]);
  const inputRef = useRef(null);

  const handleFiles = async (fileList) => {
    const pdfs = Array.from(fileList).filter((f) => f.name.toLowerCase().endsWith('.pdf'));
    if (pdfs.length === 0) return;

    setUploading(true);
    setResults([]);
    try {
      const res = await uploadFiles(pdfs);
      setResults(res.files || []);
      if (onUploaded) onUploaded(res.files || []);
    } catch (err) {
      setResults([{ filename: 'Upload failed', status: 'error', detail: err.message }]);
    }
    setUploading(false);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  return (
    <div className="p-4">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
          dragging ? 'border-black bg-gray-50' : 'border-gray-200 hover:border-gray-300'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        {uploading ? (
          <Loader2 size={24} className="mx-auto text-gray-400 animate-spin" />
        ) : (
          <Upload size={24} className="mx-auto text-gray-400" />
        )}
        <p className="text-sm text-gray-500 mt-2">
          {uploading ? 'Processing...' : 'Drop PDF files here or click to browse'}
        </p>
      </div>

      {results.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {results.map((r, i) => (
            <div key={i} className={`rounded-lg px-3 py-2 text-xs ${
              r.status === 'ok' ? 'bg-green-50 text-green-700' : r.status === 'duplicate' ? 'bg-amber-50 text-amber-700' : 'bg-red-50 text-red-700'
            }`}>
              <div className="flex items-center gap-2">
                <FileText size={13} />
                <span className="truncate flex-1">{r.filename}</span>
                {r.status === 'ok' ? <span>{r.chunk_count} chunks</span> : <span>{r.detail}</span>}
              </div>
              {r.status === 'ok' && (
                <div className="mt-2 grid grid-cols-1 gap-1.5 border-t border-green-100 pt-2">
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => onAnalyze(r, 'overview')}
                    className="flex items-center justify-center gap-1.5 rounded-md bg-emerald-600 px-2 py-1.5 font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                  >
                    <BookOpenCheck size={13} /> 一键综合精读
                  </button>
                  <div className="grid grid-cols-2 gap-1.5">
                    <button
                      type="button"
                      disabled={disabled}
                      onClick={() => onAnalyze(r, 'method')}
                      className="flex items-center justify-center gap-1 rounded-md border border-green-200 bg-white px-1 py-1.5 text-green-700 hover:bg-green-50 disabled:opacity-50"
                    >
                      <Route size={12} /> 方法解析
                    </button>
                    <button
                      type="button"
                      disabled={disabled}
                      onClick={() => onAnalyze(r, 'experiment')}
                      className="flex items-center justify-center gap-1 rounded-md border border-green-200 bg-white px-1 py-1.5 text-green-700 hover:bg-green-50 disabled:opacity-50"
                    >
                      <FlaskConical size={12} /> 实验核查
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
