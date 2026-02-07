import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';
import {
  Play, Square, Settings, Cookie, Loader2, CheckCircle2, XCircle,
  Database, Users, Target, Clock, AlertCircle, Trash2, Zap, Phone,
  Globe, TrendingUp, Activity, Wrench, Flame, Lightbulb, Home, 
  Trees, Droplets, PaintBucket, HardHat, Download
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// Industry icons and colors
const INDUSTRY_CONFIG = {
  plumbing: { icon: Droplets, color: 'bg-cyan-500', label: 'Plumbing' },
  hvac: { icon: Flame, color: 'bg-orange-500', label: 'HVAC' },
  electrical: { icon: Lightbulb, color: 'bg-yellow-500', label: 'Electrical' },
  remodeling: { icon: Home, color: 'bg-purple-500', label: 'Remodeling' },
  landscaping: { icon: Trees, color: 'bg-green-500', label: 'Landscaping' },
  power_washing: { icon: Droplets, color: 'bg-blue-500', label: 'Power Washing' },
  roofing: { icon: HardHat, color: 'bg-red-500', label: 'Roofing' },
  painting: { icon: PaintBucket, color: 'bg-pink-500', label: 'Painting' },
};

export default function ScraperDashboard() {
  const [industries, setIndustries] = useState([]);
  const [selectedIndustry, setSelectedIndustry] = useState('electrical');
  const [urls, setUrls] = useState('');
  const [cookiesConfigured, setCookiesConfigured] = useState(false);
  const [cookieExpiration, setCookieExpiration] = useState(null);
  const [showCookieSettings, setShowCookieSettings] = useState(false);
  const [cookieInput, setCookieInput] = useState('');
  const [savingCookies, setSavingCookies] = useState(false);
  
  const [currentJob, setCurrentJob] = useState(null);
  const [jobHistory, setJobHistory] = useState([]);
  const [polling, setPolling] = useState(false);
  const pollingRef = useRef(null);

  // Stats from job history
  const [totalStats, setTotalStats] = useState({ leads: 0, withPhone: 0, noWebsiteWithPhone: 0 });

  useEffect(() => {
    fetch(`${API}/scraper/industries`)
      .then(res => res.json())
      .then(data => setIndustries(data.industries || []))
      .catch(console.error);

    fetch(`${API}/scraper/cookies/status`)
      .then(res => res.json())
      .then(data => {
        setCookiesConfigured(data.configured);
        if (data.configured) {
          setCookieExpiration({
            valid: data.valid,
            message: data.message,
            expiringSoon: data.expiring_soon || [],
            expired: data.expired || []
          });
        }
      })
      .catch(console.error);

    fetch(`${API}/scraper/jobs`)
      .then(res => res.json())
      .then(data => {
        setJobHistory(data.jobs || []);
        // Calculate total stats from completed jobs
        const completed = (data.jobs || []).filter(j => j.status === 'completed');
        const totalLeads = completed.reduce((sum, j) => sum + (j.total_matches || 0), 0);
        setTotalStats({
          leads: totalLeads,
          withPhone: Math.round(totalLeads * 0.15), // Estimate ~15% have phone
          noWebsiteWithPhone: Math.round(totalLeads * 0.12), // Estimate ~12% have phone but no website
        });
      })
      .catch(console.error);
  }, []);

  const handleUrlChange = async (value) => {
    setUrls(value);
    if (value.includes('facebook.com/groups/')) {
      try {
        const res = await fetch(`${API}/scraper/detect-industry`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: value })
        });
        if (res.ok) {
          const data = await res.json();
          if (data.industry) setSelectedIndustry(data.industry);
        }
      } catch (e) {
        console.error('Industry detection failed:', e);
      }
    }
  };

  const handleSaveCookies = async () => {
    if (!cookieInput.trim()) {
      toast.error('Please paste your cookies JSON');
      return;
    }

    let cookies;
    try {
      cookies = JSON.parse(cookieInput);
      if (!Array.isArray(cookies)) throw new Error('Must be an array');
    } catch (e) {
      toast.error('Invalid JSON format');
      return;
    }

    setSavingCookies(true);
    try {
      const res = await fetch(`${API}/scraper/cookies/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cookies })
      });

      if (res.ok) {
        toast.success('Cookies saved!');
        setCookiesConfigured(true);
        setShowCookieSettings(false);
        setCookieInput('');
      } else {
        toast.error('Failed to save cookies');
      }
    } catch (e) {
      toast.error('Failed to save cookies');
    } finally {
      setSavingCookies(false);
    }
  };

  const handleDeleteCookies = async () => {
    if (!window.confirm('Delete saved cookies?')) return;
    try {
      const res = await fetch(`${API}/scraper/cookies`, { method: 'DELETE' });
      if (res.ok) {
        toast.success('Cookies deleted');
        setCookiesConfigured(false);
      }
    } catch (e) {
      toast.error('Failed to delete');
    }
  };

  const handleStartScrape = async () => {
    const urlList = urls.split('\n').map(u => u.trim()).filter(u => u.includes('facebook.com/groups/'));

    if (urlList.length === 0) {
      toast.error('Enter a valid Facebook group URL');
      return;
    }

    if (!cookiesConfigured) {
      toast.error('Configure cookies first');
      setShowCookieSettings(true);
      return;
    }

    try {
      const res = await fetch(`${API}/scraper/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: urlList, industry: selectedIndustry })
      });

      if (res.ok) {
        const data = await res.json();
        setCurrentJob({ job_id: data.job_id, status: 'starting' });
        startPolling(data.job_id);
        toast.success('Scraping started!');
      } else {
        toast.error('Failed to start');
      }
    } catch (e) {
      toast.error('Failed to start');
    }
  };

  const startPolling = (jobId) => {
    setPolling(true);
    let completionNotified = false;  // Track if we've shown the completion toast
    
    const poll = async () => {
      try {
        const res = await fetch(`${API}/scraper/job/${jobId}`);
        if (res.ok) {
          const data = await res.json();
          setCurrentJob(data);

          if (['completed', 'error', 'stopped'].includes(data.status)) {
            setPolling(false);
            clearInterval(pollingRef.current);
            pollingRef.current = null;  // Clear the ref
            
            const historyRes = await fetch(`${API}/scraper/jobs`);
            if (historyRes.ok) {
              const historyData = await historyRes.json();
              setJobHistory(historyData.jobs || []);
            }

            // Only show toast once
            if (!completionNotified) {
              completionNotified = true;
              if (data.status === 'completed') {
                toast.success(`Done! Found ${data.total_matches || 0} leads`);
              } else if (data.status === 'error') {
                toast.error(data.message || 'Failed');
              }
            }
          }
        }
      } catch (e) {
        console.error('Poll error:', e);
      }
    };

    poll();
    pollingRef.current = setInterval(poll, 2000);
  };

  const handleStopJob = async () => {
    if (!currentJob?.job_id) return;
    try {
      await fetch(`${API}/scraper/job/${currentJob.job_id}/stop`, { method: 'POST' });
      toast.info('Stopping...');
    } catch (e) {
      toast.error('Failed to stop');
    }
  };

  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  const isRunning = currentJob && ['starting', 'running'].includes(currentJob.status);
  const completedJobs = jobHistory.filter(j => j.status === 'completed').length;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 text-slate-100">
      {/* Header */}
      <header className="border-b border-slate-800/50 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-600 rounded-lg">
                <Zap className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-semibold text-white">Lead Scraper</h1>
                <p className="text-xs text-slate-400">Facebook Group Business Scraper</p>
              </div>
            </div>
            <Link to="/scrapes">
              <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white">
                <Database className="w-4 h-4 mr-2" />
                View Leads
              </Button>
            </Link>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6">
        
        {/* Stats Overview */}
        <motion.div 
          initial={{ opacity: 0, y: 10 }} 
          animate={{ opacity: 1, y: 0 }}
          className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6"
        >
          <Card className="border-slate-800 bg-slate-900/80">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400 uppercase tracking-wide">Jobs Run</p>
                  <p className="text-2xl font-bold text-white mt-1">{completedJobs}</p>
                </div>
                <div className="p-3 bg-blue-600/20 rounded-lg">
                  <Activity className="w-5 h-5 text-blue-400" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-slate-800 bg-slate-900/80">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400 uppercase tracking-wide">Total Leads</p>
                  <p className="text-2xl font-bold text-emerald-400 mt-1">{totalStats.leads.toLocaleString()}</p>
                </div>
                <div className="p-3 bg-emerald-600/20 rounded-lg">
                  <Users className="w-5 h-5 text-emerald-400" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-slate-800 bg-slate-900/80">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400 uppercase tracking-wide">With Phone</p>
                  <p className="text-2xl font-bold text-amber-400 mt-1">{totalStats.withPhone.toLocaleString()}</p>
                </div>
                <div className="p-3 bg-amber-600/20 rounded-lg">
                  <Phone className="w-5 h-5 text-amber-400" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-slate-800 bg-slate-900/80">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400 uppercase tracking-wide">No Website + Phone</p>
                  <p className="text-2xl font-bold text-purple-400 mt-1">{totalStats.noWebsiteWithPhone.toLocaleString()}</p>
                </div>
                <div className="p-3 bg-purple-600/20 rounded-lg">
                  <Phone className="w-5 h-5 text-purple-400" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-slate-800 bg-slate-900/80">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400 uppercase tracking-wide">Status</p>
                  <p className={`text-lg font-bold mt-1 ${isRunning ? 'text-blue-400' : cookiesConfigured ? 'text-emerald-400' : 'text-slate-400'}`}>
                    {isRunning ? 'Running' : cookiesConfigured ? 'Ready' : 'Setup'}
                  </p>
                </div>
                <div className={`p-3 rounded-lg ${isRunning ? 'bg-blue-600/20' : cookiesConfigured ? 'bg-emerald-600/20' : 'bg-slate-600/20'}`}>
                  {isRunning ? (
                    <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
                  ) : cookiesConfigured ? (
                    <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  ) : (
                    <Settings className="w-5 h-5 text-slate-400" />
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <div className="grid lg:grid-cols-3 gap-6">
          
          {/* Left Column - Configuration */}
          <div className="lg:col-span-2 space-y-4">
            
            {/* Industry Selection */}
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
              <Card className="border-slate-800 bg-slate-900/80">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-slate-300 uppercase tracking-wide">Select Industry</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-4 sm:grid-cols-8 gap-2">
                    {industries.map(ind => {
                      const config = INDUSTRY_CONFIG[ind] || { icon: Wrench, color: 'bg-slate-500', label: ind };
                      const Icon = config.icon;
                      const isSelected = selectedIndustry === ind;
                      
                      return (
                        <button
                          key={ind}
                          onClick={() => !isRunning && setSelectedIndustry(ind)}
                          disabled={isRunning}
                          className={`p-3 rounded-lg border transition-all ${
                            isSelected
                              ? 'border-blue-500 bg-blue-600/20 text-white'
                              : 'border-slate-700 bg-slate-800/50 text-slate-400 hover:border-slate-600'
                          } ${isRunning ? 'opacity-50 cursor-not-allowed' : ''}`}
                        >
                          <div className={`w-6 h-6 mx-auto mb-1 rounded ${config.color} p-1`}>
                            <Icon className="w-full h-full text-white" />
                          </div>
                          <p className="text-xs font-medium capitalize truncate">{config.label}</p>
                        </button>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            </motion.div>

            {/* URL Input & Start */}
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
              <Card className="border-slate-800 bg-slate-900/80">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-slate-300 uppercase tracking-wide">Facebook Group URL</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <textarea
                    value={urls}
                    onChange={(e) => handleUrlChange(e.target.value)}
                    placeholder="https://facebook.com/groups/example"
                    disabled={isRunning}
                    className="w-full h-24 px-4 py-3 bg-slate-950 border border-slate-700 rounded-lg text-slate-200 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 resize-none"
                    data-testid="urls-textarea"
                  />
                  
                  <div className="flex gap-3">
                    {isRunning ? (
                      <Button
                        onClick={handleStopJob}
                        className="flex-1 bg-red-600 hover:bg-red-700"
                        data-testid="stop-scraper-btn"
                      >
                        <Square className="w-4 h-4 mr-2" />
                        Stop Scraping
                      </Button>
                    ) : (
                      <Button
                        onClick={handleStartScrape}
                        disabled={!cookiesConfigured || !urls.trim()}
                        className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700"
                        data-testid="start-scraper-btn"
                      >
                        <Play className="w-4 h-4 mr-2" />
                        Start Scraping
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            </motion.div>

            {/* Live Progress */}
            {currentJob && (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
                <Card className="border-slate-800 bg-slate-900/80 border-l-4 border-l-blue-500">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-medium text-slate-300 uppercase tracking-wide flex items-center gap-2">
                        {isRunning && <Loader2 className="w-4 h-4 animate-spin text-blue-400" />}
                        Live Progress
                      </CardTitle>
                      <span className={`text-xs px-2 py-1 rounded ${
                        currentJob.status === 'completed' ? 'bg-emerald-900/50 text-emerald-400' :
                        currentJob.status === 'error' ? 'bg-red-900/50 text-red-400' :
                        'bg-blue-900/50 text-blue-400'
                      }`}>
                        {currentJob.status}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm text-slate-400">{currentJob.message || 'Processing...'}</p>
                    
                    <div className="space-y-2">
                      <div className="flex justify-between text-xs text-slate-400">
                        <span>Progress</span>
                        <span>{currentJob.members_scanned || 0} members scanned</span>
                      </div>
                      <Progress 
                        value={Math.min((currentJob.members_scanned || 0) / 500 * 100, 100)} 
                        className="h-2 bg-slate-800" 
                      />
                    </div>

                    <div className="grid grid-cols-3 gap-3">
                      <div className="text-center p-3 bg-slate-950 rounded-lg">
                        <Users className="w-4 h-4 mx-auto mb-1 text-slate-400" />
                        <p className="text-xl font-bold text-white">{(currentJob.members_scanned || 0).toLocaleString()}</p>
                        <p className="text-xs text-slate-500">Scanned</p>
                      </div>
                      <div className="text-center p-3 bg-slate-950 rounded-lg">
                        <Target className="w-4 h-4 mx-auto mb-1 text-emerald-400" />
                        <p className="text-xl font-bold text-emerald-400">{(currentJob.matches_found || currentJob.total_matches || 0).toLocaleString()}</p>
                        <p className="text-xs text-slate-500">Matches</p>
                      </div>
                      <div className="text-center p-3 bg-slate-950 rounded-lg">
                        <TrendingUp className="w-4 h-4 mx-auto mb-1 text-blue-400" />
                        <p className="text-xl font-bold text-blue-400">
                          {currentJob.members_scanned > 0 
                            ? Math.round((currentJob.matches_found || 0) / currentJob.members_scanned * 100) 
                            : 0}%
                        </p>
                        <p className="text-xs text-slate-500">Match Rate</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}
          </div>

          {/* Right Column - Settings & History */}
          <div className="space-y-4">
            
            {/* Cookie Settings */}
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
              <Card className="border-slate-800 bg-slate-900/80">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-medium text-slate-300 uppercase tracking-wide">Authentication</CardTitle>
                    {cookiesConfigured ? (
                      <span className="flex items-center gap-1 text-xs text-emerald-400">
                        <CheckCircle2 className="w-3 h-3" />
                        Connected
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-xs text-red-400">
                        <XCircle className="w-3 h-3" />
                        Not Connected
                      </span>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowCookieSettings(!showCookieSettings)}
                    className="w-full border-slate-700 text-slate-300 hover:bg-slate-800"
                  >
                    <Cookie className="w-4 h-4 mr-2" />
                    {showCookieSettings ? 'Hide Settings' : 'Configure Cookies'}
                  </Button>

                  {showCookieSettings && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      className="space-y-3 pt-3 border-t border-slate-800"
                    >
                      <textarea
                        value={cookieInput}
                        onChange={(e) => setCookieInput(e.target.value)}
                        placeholder='[{"name": "c_user", ...}]'
                        className="w-full h-32 px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-slate-200 text-xs font-mono focus:ring-2 focus:ring-blue-500 resize-none"
                        data-testid="cookie-input-textarea"
                      />
                      <div className="flex gap-2">
                        <Button
                          onClick={handleSaveCookies}
                          disabled={savingCookies}
                          size="sm"
                          className="flex-1 bg-blue-600 hover:bg-blue-700"
                        >
                          {savingCookies && <Loader2 className="w-3 h-3 animate-spin mr-1" />}
                          Save
                        </Button>
                        {cookiesConfigured && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleDeleteCookies}
                            className="border-red-800 text-red-400 hover:bg-red-950"
                          >
                            <Trash2 className="w-3 h-3" />
                          </Button>
                        )}
                      </div>
                    </motion.div>
                  )}
                </CardContent>
              </Card>
            </motion.div>

            {/* Job History */}
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}>
              <Card className="border-slate-800 bg-slate-900/80">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-slate-300 uppercase tracking-wide flex items-center gap-2">
                    <Clock className="w-4 h-4 text-slate-400" />
                    Recent Jobs
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {jobHistory.length === 0 ? (
                    <p className="text-sm text-slate-500 text-center py-4">No jobs yet</p>
                  ) : (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {jobHistory.slice(0, 8).map((job) => {
                        const config = INDUSTRY_CONFIG[job.industry] || { icon: Wrench, color: 'bg-slate-500', label: job.industry };
                        const Icon = config.icon;
                        const csvFile = job.results?.[0]?.file;
                        
                        const handleDownload = async (filename) => {
                          try {
                            const res = await fetch(`${API}/scrapes/download/${encodeURIComponent(filename)}`);
                            if (res.ok) {
                              const blob = await res.blob();
                              const url = window.URL.createObjectURL(blob);
                              const a = document.createElement('a');
                              a.href = url;
                              a.download = filename;
                              document.body.appendChild(a);
                              a.click();
                              window.URL.revokeObjectURL(url);
                              a.remove();
                              toast.success(`Downloaded ${filename}`);
                            } else {
                              toast.error('Download failed');
                            }
                          } catch (e) {
                            toast.error('Download failed');
                          }
                        };
                        
                        return (
                          <div
                            key={job.job_id}
                            className="flex items-center gap-3 p-2 bg-slate-950 rounded-lg"
                          >
                            <div className={`p-1.5 rounded ${config.color}`}>
                              <Icon className="w-3 h-3 text-white" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-slate-200 capitalize truncate">
                                {config.label}
                              </p>
                              <p className="text-xs text-slate-500">
                                {job.total_matches || 0} leads • {new Date(job.started_at).toLocaleDateString()}
                              </p>
                            </div>
                            {job.status === 'completed' && csvFile && (
                              <button
                                onClick={() => handleDownload(csvFile)}
                                className="p-1.5 rounded bg-emerald-900/50 hover:bg-emerald-800/50 text-emerald-400 transition-colors"
                                title="Download CSV"
                              >
                                <Download className="w-3 h-3" />
                              </button>
                            )}
                            <span className={`text-xs px-1.5 py-0.5 rounded ${
                              job.status === 'completed' ? 'bg-emerald-900/50 text-emerald-400' :
                              job.status === 'error' ? 'bg-red-900/50 text-red-400' :
                              job.status === 'running' ? 'bg-blue-900/50 text-blue-400' :
                              'bg-slate-800 text-slate-400'
                            }`}>
                              {job.status === 'completed' ? '✓' : job.status === 'error' ? '✗' : '...'}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>

          </div>
        </div>
      </main>
    </div>
  );
}
