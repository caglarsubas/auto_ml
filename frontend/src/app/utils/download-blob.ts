/** Keep the object URL alive while the browser dispatches its download. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.appendChild(link);
  try {
    link.click();
  } finally {
    link.remove();
    // Revoking synchronously can invalidate an asynchronously dispatched download.
    // This is cleanup only: no request retry, automatic action or download delay.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
