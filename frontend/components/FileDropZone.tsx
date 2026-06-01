"use client";

import React, { useCallback } from "react";
import { useDropzone } from "react-dropzone";

interface FileDropZoneProps {
  label?: string;
  file: File | null;
  onFileChange: (file: File | null) => void;
  error?: string;
  disabled?: boolean;
}

export function FileDropZone({
  label = "Upload File",
  file,
  onFileChange,
  error,
  disabled = false,
}: FileDropZoneProps) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length > 0) {
        const selectedFile = acceptedFiles[0];
        if (selectedFile.size <= 10 * 1024 * 1024) {
          onFileChange(selectedFile);
        }
      }
    },
    [onFileChange]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024,
    disabled,
  });

  return (
    <div>
      <label className="block text-sm font-medium mb-1">{label}</label>
      <div
        {...getRootProps()}
        className={`p-8 border-2 border-dashed rounded-md cursor-pointer transition-colors ${
          isDragActive
            ? "border-blue-500 bg-blue-50"
            : disabled
            ? "border-gray-200 bg-gray-50"
            : "border-gray-300 hover:border-blue-400"
        } ${error ? "border-red-500" : ""}`}
      >
        <input {...getInputProps()} />
        {file ? (
          <div className="text-center">
            <svg
              className="mx-auto h-12 w-12 text-green-500"
              stroke="currentColor"
              fill="none"
              viewBox="0 0 48 48"
              aria-hidden="true"
            >
              <path
                d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <p className="mt-2 text-sm text-gray-600">{file.name}</p>
            <p className="mt-1 text-xs text-gray-500">
              {Math.round(file.size / 1024)} KB
            </p>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onFileChange(null);
              }}
              className="mt-2 text-xs text-blue-600 hover:underline"
            >
              Remove
            </button>
          </div>
        ) : (
          <div className="text-center">
            <svg
              className="mx-auto h-12 w-12 text-gray-400"
              stroke="currentColor"
              fill="none"
              viewBox="0 0 48 48"
              aria-hidden="true"
            >
              <path
                d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <p className="mt-2 text-sm text-gray-600">
              Drag and drop a PDF file here, or click to select
            </p>
            <p className="mt-1 text-xs text-gray-500">
              Maximum file size: 10 MB
            </p>
          </div>
        )}
      </div>
      {error && <p className="text-red-600 text-sm mt-1">{error}</p>}
    </div>
  );
}
