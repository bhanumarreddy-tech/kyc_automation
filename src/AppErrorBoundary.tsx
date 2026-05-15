import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Shows a readable recovery UI instead of a blank screen when React throws during render.
 */
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[AppErrorBoundary]", error, info.componentStack);
  }

  override render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="min-h-screen bg-background text-foreground p-6 md:p-10 font-sans">
          <h1 className="text-xl font-semibold mb-2">UI failed to load</h1>
          <p className="text-muted-foreground text-sm mb-4">
            Something threw while rendering this page. If you&apos;re troubleshooting, details are below —
            reload after fixing the underlying error.
          </p>
          <pre className="text-xs whitespace-pre-wrap bg-muted p-4 rounded-md border max-w-4xl mb-6">
            {this.state.error.message}
          </pre>
          <button
            type="button"
            className="inline-flex h-10 items-center rounded-md bg-primary px-4 text-primary-foreground text-sm font-medium"
            onClick={() => window.location.reload()}
          >
            Reload page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
