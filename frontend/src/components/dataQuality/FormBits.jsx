export function StatusMessage({ error, message }) {
  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }
  if (message) {
    return <p className="text-sm text-muted-foreground">{message}</p>;
  }
  return null;
}

export function Field({ label, children }) {
  return (
    <label className="grid gap-1 text-xs font-medium text-muted-foreground">
      <span>{label}</span>
      {children}
    </label>
  );
}
