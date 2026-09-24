import type { Metadata } from "next";

import { ImportUploadView } from "@/components/imports/import-upload";

export const metadata: Metadata = { title: "Import jobs" };

export default function NewImportPage() {
  return <ImportUploadView />;
}
