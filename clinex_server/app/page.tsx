"use client";

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Lock, Cpu, Globe, ChevronRight } from 'lucide-react';
import { useRouter } from 'next/navigation';

export default function Home() {
  const router = useRouter();
  const [computerCode, setComputerCode] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    // Simulate API call to pair with the local agent
    // In a real app, you would hit /api/pair to verify credentials against DB/KV
    setTimeout(() => {
      setLoading(false);
      // For demo purposes, we accept any format that looks valid
      if (computerCode.length > 5 && password.length > 5) {
        // Redirect to the tunnel dashboard
        router.push('/tunnel/dashboard');
      } else {
        alert("Invalid credentials. (Try entering longer strings for demo)");
      }
    }, 1500);
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-white flex flex-col items-center justify-center p-4 relative overflow-hidden">
      {/* Background Gradients */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-500/10 rounded-full blur-[100px]" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-500/10 rounded-full blur-[100px]" />

      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md relative z-10"
      >
        <div className="text-center mb-10">
            <div className="w-16 h-16 bg-gradient-to-br from-blue-600 to-purple-600 rounded-2xl mx-auto flex items-center justify-center mb-6 shadow-xl shadow-blue-500/20">
                <Globe className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-4xl font-bold tracking-tight mb-2 bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-400">
                Cline X Server
            </h1>
            <p className="text-gray-500">Secure Remote Access Gateway</p>
        </div>

        <form onSubmit={handleLogin} className="bg-[#111] border border-gray-800 rounded-2xl p-8 shadow-2xl space-y-5 backdrop-blur-xl">
            <div className="space-y-2">
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Computer Code</label>
                <div className="relative">
                    <Cpu className="absolute left-3 top-3 w-5 h-5 text-gray-500" />
                    <input 
                        type="text" 
                        value={computerCode}
                        onChange={(e) => setComputerCode(e.target.value)}
                        placeholder="XXX-XXX-XXX"
                        className="w-full bg-[#1A1A1A] border border-gray-700 rounded-lg pl-10 pr-4 py-3 text-gray-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder-gray-600"
                        required
                    />
                </div>
            </div>

            <div className="space-y-2">
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Pairing Password</label>
                <div className="relative">
                    <Lock className="absolute left-3 top-3 w-5 h-5 text-gray-500" />
                    <input 
                        type="password" 
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••••••"
                        className="w-full bg-[#1A1A1A] border border-gray-700 rounded-lg pl-10 pr-4 py-3 text-gray-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder-gray-600"
                        required
                    />
                </div>
            </div>

            <div className="pt-2">
                <button 
                    type="submit" 
                    disabled={loading}
                    className="w-full bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white font-semibold py-3 rounded-lg transition-all flex items-center justify-center gap-2 group disabled:opacity-50"
                >
                    {loading ? (
                        <span>Connecting...</span>
                    ) : (
                        <>
                            <span>Connect to Session</span>
                            <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                        </>
                    )}
                </button>
            </div>
            
            <p className="text-center text-xs text-gray-600 mt-4">
                Encrypted End-to-End • Vercel Secure Relay
            </p>
        </form>
      </motion.div>
    </div>
  );
}
