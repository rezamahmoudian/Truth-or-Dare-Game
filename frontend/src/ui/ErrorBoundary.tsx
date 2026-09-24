/* eslint-disable react-refresh/only-export-components --
   An error boundary has to be a class: React offers no hook for
   componentDidCatch. Class components are not fast-refreshable, so this
   rule can never be satisfied here. */
import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/ui/Button";

/**
 * Catches render errors so one broken screen does not take the whole app down.
 *
 * Without this, any exception thrown while rendering unmounts the entire React
 * tree and leaves a white page — no message, no tab bar, no way back. That is
 * the worst possible failure on a phone, because the only remaining move is to
 * close the app, and a lot of people do not come back from that.
 *
 * `resetKey` is how the boundary un-sticks itself: when it changes (the route,
 * in practice) the boundary drops the error and tries to render again, so
 * navigating away from a broken screen is enough to recover.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode; resetKey?: string; fallback?: (retry: () => void) => ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // The console is the only reporter this app has. If a crash reporter is
    // ever added, this is the one place that needs to know about it.
    console.error("[ui] render crashed", error, info.componentStack);
  }

  componentDidUpdate(previous: { resetKey?: string }) {
    if (this.state.error && previous.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  retry = () => this.setState({ error: null });

  render() {
    if (!this.state.error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(this.retry);
    return <CrashScreen error={this.state.error} onRetry={this.retry} />;
  }
}

function CrashScreen({ error, onRetry }: { error: Error; onRetry: () => void }) {
  return (
    <div className="flex h-[100dvh] items-center justify-center px-6">
      <div className="animate-fade-in flex w-full max-w-sm flex-col items-center gap-4 text-center">
        <span className="grid size-20 place-items-center rounded-full bg-surface-2 text-4xl">
          🙃
        </span>
        <p className="text-[17px] font-bold">یک جای کار ایراد داشت</p>
        <p className="text-[14px] leading-relaxed text-muted">
          این صفحه باز نشد. گفتگوها و دوستانت سر جایشان هستند.
        </p>

        {import.meta.env.DEV && (
          // Only in development: a user has no use for a stack trace, but a
          // developer staring at a blank phone screen very much does.
          <pre
            dir="ltr"
            className="max-h-40 w-full overflow-auto rounded-lg bg-surface-2 p-3 text-start text-[11px] leading-relaxed text-faint"
          >
            {error.message}
          </pre>
        )}

        <div className="mt-1 flex w-full flex-col gap-2">
          <Button onClick={onRetry}>دوباره امتحان کن</Button>
          <Button variant="ghost" onClick={() => window.location.assign("/")}>
            برگرد به خانه
          </Button>
        </div>
      </div>
    </div>
  );
}
