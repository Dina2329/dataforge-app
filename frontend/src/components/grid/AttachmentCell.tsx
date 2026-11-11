import { useRef } from "react";
import { Paperclip, Plus, X } from "lucide-react";
import type { Attachment } from "../../types";
import { useDeleteAttachment, useDownloadAttachment, useUploadAttachment } from "../../hooks/useRecords";

interface AttachmentCellProps {
  tableId: string;
  rowId: number;
  fieldId: string;
  value: unknown;
}

export function AttachmentCell({ tableId, rowId, fieldId, value }: AttachmentCellProps) {
  const files = (value as Attachment[] | null) ?? [];
  const fileInputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadAttachment(tableId);
  const deleteAttachment = useDeleteAttachment(tableId);
  const download = useDownloadAttachment(tableId);

  function handleFilePicked(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    upload.mutate({ rowId, fieldId, file });
  }

  return (
    <div className="flex h-full items-center gap-1 overflow-x-auto px-1.5" onClick={(e) => e.stopPropagation()}>
      {files.map((file) => (
        <span
          key={file.id}
          className="group/chip flex shrink-0 cursor-pointer items-center gap-1 rounded bg-surface-raised px-1.5 py-0.5 text-xs text-ink-secondary hover:bg-accent-secondary-tint hover:text-accent-secondary"
          title={`${file.filename} (${Math.max(1, Math.round(file.size / 1024))} KB) — click to download`}
          onClick={() => download.mutate({ rowId, fieldId, attachmentId: file.id, filename: file.filename })}
        >
          <Paperclip className="size-3 shrink-0" />
          <span className="max-w-20 truncate">{file.filename}</span>
          <button
            type="button"
            className="shrink-0 rounded p-0.5 text-ink-tertiary opacity-0 hover:bg-status-danger-tint hover:text-status-danger group-hover/chip:opacity-100"
            title="Remove"
            onClick={(e) => {
              e.stopPropagation();
              deleteAttachment.mutate({ rowId, fieldId, attachmentId: file.id });
            }}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input ref={fileInputRef} type="file" className="hidden" onChange={handleFilePicked} />
      <button
        type="button"
        className="flex shrink-0 items-center justify-center rounded p-1 text-ink-tertiary hover:bg-surface-raised hover:text-accent-secondary disabled:opacity-50"
        title="Add attachment"
        disabled={upload.isPending}
        onClick={() => fileInputRef.current?.click()}
      >
        <Plus className="size-3.5" />
      </button>
    </div>
  );
}
