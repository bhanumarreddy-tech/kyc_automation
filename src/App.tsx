import { Suspense } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppErrorBoundary } from "./AppErrorBoundary";
import Index from "./pages/Index";
import IntakeEntry from "./pages/IntakeEntry";
import KYCAutomation from "./pages/KYCAutomation";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <AppErrorBoundary>
          <Suspense
            fallback={
              <div className="min-h-screen flex items-center justify-center bg-background text-muted-foreground text-sm">
                Loading…
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<Index />} />
              <Route path="/intake/:token" element={<IntakeEntry />} />
              <Route path="/kyc" element={<KYCAutomation />} />
              <Route path="/auth" element={<Navigate to="/kyc" replace />} />
              <Route path="/learn-more" element={<Navigate to="/" replace />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </AppErrorBoundary>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
