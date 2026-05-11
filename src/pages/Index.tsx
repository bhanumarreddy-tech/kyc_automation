import { Button } from "@/components/ui/button";
import { ArrowRight, Shield, Zap, CheckCircle2, Upload } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState, useRef } from "react";
import heroBg from "@/assets/kyc-hero-bg.jpg";
import tigerLogo from "@/assets/tiger-analytics-logo.png";
import clientLogo from "@/assets/client-logo-placeholder.png";

export default function Index() {
  const navigate = useNavigate();
  const [uploadedClientLogo, setUploadedClientLogo] = useState<string | null>(() => {
    return localStorage.getItem('clientLogo');
  });
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleLogoClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        const logoData = reader.result as string;
        setUploadedClientLogo(logoData);
        localStorage.setItem('clientLogo', logoData);
      };
      reader.readAsDataURL(file);
    }
  };

  return (
    <div className="min-h-screen relative overflow-hidden bg-gradient-to-br from-tiger-dark via-tiger-charcoal to-tiger-dark">
      {/* Animated background overlay */}
      <div className="absolute inset-0 bg-gradient-to-br from-tiger-orange/10 via-tiger-orange/5 to-tiger-orange/10 animate-pulse" />
      
      {/* Hero Background Image with overlay */}
      <div 
        className="absolute inset-0 bg-cover bg-center opacity-20"
        style={{ backgroundImage: `url(${heroBg})` }}
      />
      
      {/* Animated grid pattern */}
      <div className="absolute inset-0 bg-[linear-gradient(hsl(var(--tiger-orange)/0.05)_1px,transparent_1px),linear-gradient(90deg,hsl(var(--tiger-orange)/0.05)_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_80%_50%_at_50%_50%,black,transparent)]" />
      
      {/* Header with Logos */}
      <div className="absolute top-0 left-0 right-0 z-20 px-8 py-6">
        <div className="container mx-auto flex justify-between items-center">
          <div 
            className="w-32 h-16 flex items-center cursor-pointer group relative"
            onClick={handleLogoClick}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              className="hidden"
            />
            <img 
              src={uploadedClientLogo || clientLogo} 
              alt="Client Logo" 
              className="max-w-full max-h-full object-contain opacity-60 group-hover:opacity-100 transition-opacity" 
            />
            <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/50 rounded">
              <Upload className="h-6 w-6 text-white" />
            </div>
          </div>
          <div className="w-40 h-20 flex items-center">
            <img src={tigerLogo} alt="Tiger Analytics" className="max-w-full max-h-full object-contain" />
          </div>
        </div>
      </div>
      
      {/* Content */}
      <div className="relative z-10 container mx-auto px-4 py-16">
        <div className="flex flex-col items-center justify-center min-h-screen text-center space-y-12">
          {/* Logo/Brand */}
          <div className="space-y-4 animate-fade-in">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-tiger-orange/10 border border-tiger-orange/20 backdrop-blur-sm">
              <Shield className="h-4 w-4 text-tiger-orange" />
              <span className="text-sm font-medium text-tiger-orange">AI powered, Enterprise Grade Security</span>
            </div>
          </div>

          {/* Main Headline */}
          <div className="space-y-6 max-w-5xl animate-fade-in [animation-delay:200ms]">
            <h1 className="text-7xl md:text-8xl font-bold tracking-tight">
              <span className="text-tiger-orange">
                Tiger Analytics
              </span>
            </h1>
            <h2 className="text-4xl md:text-5xl font-bold text-white">
              KYC Automation Platform
            </h2>
            <p className="text-xl md:text-2xl text-muted-foreground max-w-3xl mx-auto leading-relaxed">
              Revolutionize your commercial banking compliance with AI-powered document analysis and automated KYC processing
            </p>
          </div>

          {/* Features */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl w-full animate-fade-in [animation-delay:400ms]">
            <div className="p-6 rounded-2xl bg-white/5 backdrop-blur-sm border border-white/10 hover:bg-white/10 transition-all duration-300 hover:scale-105 group">
              <div className="flex flex-col items-center gap-4">
                <div className="p-3 rounded-xl bg-tiger-orange/10 group-hover:bg-tiger-orange/20 transition-colors">
                  <Zap className="h-8 w-8 text-tiger-orange" />
                </div>
                <div className="space-y-2">
                  <h3 className="text-xl font-semibold text-white">Lightning Fast</h3>
                  <p className="text-sm text-muted-foreground">Process documents in seconds with AI-powered extraction</p>
                </div>
              </div>
            </div>

            <div className="p-6 rounded-2xl bg-white/5 backdrop-blur-sm border border-white/10 hover:bg-white/10 transition-all duration-300 hover:scale-105 group">
              <div className="flex flex-col items-center gap-4">
                <div className="p-3 rounded-xl bg-tiger-orange/10 group-hover:bg-tiger-orange/20 transition-colors">
                  <CheckCircle2 className="h-8 w-8 text-tiger-orange" />
                </div>
                <div className="space-y-2">
                  <h3 className="text-xl font-semibold text-white">99% Accuracy</h3>
                  <p className="text-sm text-muted-foreground">Advanced AI models ensure precise data extraction</p>
                </div>
              </div>
            </div>

            <div className="p-6 rounded-2xl bg-white/5 backdrop-blur-sm border border-white/10 hover:bg-white/10 transition-all duration-300 hover:scale-105 group">
              <div className="flex flex-col items-center gap-4">
                <div className="p-3 rounded-xl bg-tiger-orange/10 group-hover:bg-tiger-orange/20 transition-colors">
                  <Shield className="h-8 w-8 text-tiger-orange" />
                </div>
                <div className="space-y-2">
                  <h3 className="text-xl font-semibold text-white">Bank-Grade Security</h3>
                  <p className="text-sm text-muted-foreground">Enterprise security with complete compliance</p>
                </div>
              </div>
            </div>
          </div>

          {/* CTA */}
          <div className="flex flex-col sm:flex-row gap-4 animate-fade-in [animation-delay:600ms]">
            <Button
              size="lg"
              onClick={() => navigate("/kyc")}
              className="text-lg px-8 py-6 rounded-xl bg-tiger-dark hover:bg-tiger-charcoal shadow-[0_0_30px_hsl(var(--tiger-orange)/0.3)] hover:shadow-[0_0_50px_hsl(var(--tiger-orange)/0.5)] transition-all duration-300 group"
            >
              Start KYC Processing
              <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
            </Button>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-8 max-w-2xl w-full pt-12 border-t border-white/10 animate-fade-in [animation-delay:800ms]">
            <div className="text-center">
              <div className="text-3xl font-bold text-tiger-orange">500K+</div>
              <div className="text-sm text-muted-foreground mt-1">Documents Processed</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-tiger-orange">98%</div>
              <div className="text-sm text-muted-foreground mt-1">Time Saved</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-tiger-orange">24/7</div>
              <div className="text-sm text-muted-foreground mt-1">Support Available</div>
            </div>
          </div>
        </div>
      </div>

      {/* Floating particles effect */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {[...Array(20)].map((_, i) => (
          <div
            key={i}
            className="absolute w-1 h-1 bg-tiger-orange/30 rounded-full animate-float"
            style={{
              left: `${Math.random() * 100}%`,
              top: `${Math.random() * 100}%`,
              animationDelay: `${Math.random() * 6}s`,
            }}
          />
        ))}
      </div>
    </div>
  );
}
