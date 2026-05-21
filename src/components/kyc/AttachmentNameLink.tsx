import { attachmentDownloadUrl } from "@/lib/kycPageUtils";
import type { AttachedDocumentItem } from "@/types/kycHistory";

interface AttachmentNameLinkProps {
  submissionId: string;
  doc: AttachedDocumentItem;
  className?: string;
}

export function AttachmentNameLink({ submissionId, doc, className }: AttachmentNameLinkProps) {
  if (!doc.objectKey) {
    return <span className={className}>{doc.filename}</span>;
  }
  return (
    <a
      href={attachmentDownloadUrl(submissionId, doc.objectKey)}
      className={`text-primary underline-offset-4 hover:underline font-medium ${className ?? ""}`}
    >
      {doc.filename}
    </a>
  );
}
