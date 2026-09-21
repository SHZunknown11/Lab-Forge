import { useState, useEffect } from "react"
import { Toaster, toast } from "sonner"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { DotPattern } from "@/components/ui/dot-pattern"
import { Loader2, LogOut, FileText, Upload } from "lucide-react"
import { ThemeProvider } from "@/components/theme-provider"
import { ModeToggle } from "@/components/mode-toggle"

const API_BASE = "http://localhost:8000/api"

export default function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem("labforge_token"))
  const [loading, setLoading] = useState(false)
  const [profile, setProfile] = useState<any>(null)

  // Auth form states
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  
  // Signup extra states
  const [name, setName] = useState("")
  const [uid, setUid] = useState("")
  const [batch, setBatch] = useState("")

  // Dashboard states
  const [file, setFile] = useState<File | null>(null)
  const [subjectCode, setSubjectCode] = useState("")
  const [subjectName, setSubjectName] = useState("")
  const [forceRefresh, setForceRefresh] = useState(false)
  const [generating, setGenerating] = useState(false)

  useEffect(() => {
    if (token) {
      fetchProfile()
    }
  }, [token])

  const fetchProfile = async () => {
    try {
      const res = await fetch(`${API_BASE}/profiles`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.status === 401) {
        handleLogout()
        toast.error("Session expired")
        return
      }
      const data = await res.json()
      setProfile(data)
      if (data.subject_code) setSubjectCode(data.subject_code)
      if (data.subject_name) setSubjectName(data.subject_name)
    } catch (err) {
      toast.error("Failed to fetch profile")
    }
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      })
      if (!res.ok) throw new Error("Invalid credentials")
      const data = await res.json()
      localStorage.setItem("labforge_token", data.access_token)
      setToken(data.access_token)
      toast.success("Welcome back!")
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          username, 
          password, 
          student_name: name,
          uid,
          batch 
        })
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || "Signup failed")
      }
      
      // Auto login
      const loginRes = await fetch(`${API_BASE}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      })
      if (!loginRes.ok) throw new Error("Signup succeeded but login failed")
      const data = await loginRes.json()
      
      localStorage.setItem("labforge_token", data.access_token)
      setToken(data.access_token)
      toast.success("Account created successfully")
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem("labforge_token")
    setToken(null)
    setProfile(null)
  }

  const handleGenerate = async () => {
    if (!file) {
      toast.error("Please upload a source file")
      return
    }
    setGenerating(true)
    try {
      const formData = new FormData()
      formData.append("file", file)
      formData.append("subject_code", subjectCode)
      formData.append("subject_name", subjectName)
      formData.append("force_refresh", String(forceRefresh))

      const res = await fetch(`${API_BASE}/generate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      })
      
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || "Generation failed")
      }
      
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Lab_Report_${subjectCode || 'General'}.docx`
      a.click()
      toast.success("Report generated successfully!")
      fetchProfile() // Refresh quota
    } catch (err: any) {
      toast.error(err.message)
    } finally {
      setGenerating(false)
    }
  }

  if (!token) {
    return (
      <ThemeProvider defaultTheme="dark" storageKey="labforge-ui-theme">
        <div className="relative flex min-h-screen items-center justify-center bg-background text-foreground overflow-hidden font-sans">
          <DotPattern className="opacity-30 dark:opacity-20" />
          <div className="absolute top-4 right-4 z-50">
            <ModeToggle />
          </div>
          <div className="z-10 w-full max-w-md px-4">
            <div className="mb-8 text-center">
              <h1 className="text-4xl font-bold tracking-tighter text-foreground mb-2">LabForge</h1>
              <p className="text-muted-foreground text-sm">Minimalist university report generator</p>
            </div>
            
            <Tabs defaultValue="login" className="w-full">
              <TabsList className="grid w-full grid-cols-2 mb-6 h-12 rounded-xl p-1 bg-muted">
                <TabsTrigger value="login" className="rounded-lg h-full">Login</TabsTrigger>
                <TabsTrigger value="signup" className="rounded-lg h-full">Sign Up</TabsTrigger>
              </TabsList>
              
              <TabsContent value="login">
                <Card className="border-border shadow-sm">
                  <form onSubmit={handleLogin}>
                    <CardHeader className="space-y-1">
                      <CardTitle className="text-2xl font-bold">Welcome back</CardTitle>
                      <CardDescription>Enter your credentials to access your workspace.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="username">Username</Label>
                        <Input id="username" type="text" required value={username} onChange={e => setUsername(e.target.value)} className="h-11" />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="password">Password</Label>
                        <Input id="password" type="password" required value={password} onChange={e => setPassword(e.target.value)} className="h-11" />
                      </div>
                    </CardContent>
                    <CardFooter>
                      <Button type="submit" className="w-full h-11 text-base font-medium transition-all" disabled={loading}>
                        {loading && <Loader2 className="mr-2 h-5 w-5 animate-spin" />}
                        Sign In
                      </Button>
                    </CardFooter>
                  </form>
                </Card>
              </TabsContent>

              <TabsContent value="signup">
                <Card className="border-border shadow-sm">
                  <form onSubmit={handleSignup}>
                    <CardHeader className="space-y-1">
                      <CardTitle className="text-2xl font-bold">Create an account</CardTitle>
                      <CardDescription>Start automating your lab reports in seconds.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="signup-user">Username</Label>
                          <Input id="signup-user" required value={username} onChange={e => setUsername(e.target.value)} className="h-11" />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="signup-pass">Password</Label>
                          <Input id="signup-pass" type="password" required value={password} onChange={e => setPassword(e.target.value)} className="h-11" />
                        </div>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="name">Full Name</Label>
                        <Input id="name" placeholder="John Doe" value={name} onChange={e => setName(e.target.value)} className="h-11" />
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="uid">Roll No / UID</Label>
                          <Input id="uid" value={uid} onChange={e => setUid(e.target.value)} className="h-11" />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="batch">Batch / Section</Label>
                          <Input id="batch" value={batch} onChange={e => setBatch(e.target.value)} className="h-11" />
                        </div>
                      </div>
                      <p className="text-xs text-muted-foreground text-center pt-2">
                        These will be used as defaults for generated reports.
                      </p>
                    </CardContent>
                    <CardFooter>
                      <Button type="submit" className="w-full h-11 text-base font-medium transition-all" disabled={loading}>
                        {loading && <Loader2 className="mr-2 h-5 w-5 animate-spin" />}
                        Create Account
                      </Button>
                    </CardFooter>
                  </form>
                </Card>
              </TabsContent>
            </Tabs>
          </div>
          <Toaster />
        </div>
      </ThemeProvider>
    )
  }

  return (
    <ThemeProvider defaultTheme="dark" storageKey="labforge-ui-theme">
      <div className="min-h-screen bg-background text-foreground font-sans">
        <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6 lg:px-8">
            <div className="flex items-center gap-2">
              <FileText className="h-6 w-6 text-primary" />
              <h1 className="text-xl font-bold tracking-tight">LabForge</h1>
            </div>
            <div className="flex items-center gap-4">
              <span className="hidden sm:inline-block text-sm font-medium text-muted-foreground bg-muted px-3 py-1.5 rounded-full">
                {profile ? `${profile.generations_today || 0} / ${profile.generation_limit} used today` : 'Loading quota...'}
              </span>
              <ModeToggle />
              <Button variant="ghost" size="icon" onClick={handleLogout} className="text-muted-foreground hover:text-foreground h-11 w-11 rounded-xl">
                <LogOut className="h-5 w-5" />
                <span className="sr-only">Sign out</span>
              </Button>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 py-8 space-y-8">
          <div className="grid md:grid-cols-2 gap-6">
            <Card className="border-border shadow-sm">
              <CardHeader>
                <CardTitle className="text-xl">Profile Defaults</CardTitle>
                <CardDescription>Your details embedded in reports.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex justify-between items-center text-sm border-b border-border pb-3">
                  <span className="text-muted-foreground font-medium">Name</span>
                  <span className="font-semibold">{profile?.student_name || 'Not set'}</span>
                </div>
                <div className="flex justify-between items-center text-sm border-b border-border pb-3">
                  <span className="text-muted-foreground font-medium">UID</span>
                  <span className="font-semibold">{profile?.uid || 'Not set'}</span>
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-muted-foreground font-medium">Batch</span>
                  <span className="font-semibold">{profile?.batch || 'Not set'}</span>
                </div>
              </CardContent>
            </Card>

            <Card className="border-border shadow-sm">
              <CardHeader>
                <CardTitle className="text-xl">Subject Info</CardTitle>
                <CardDescription>Configure the subject for this report.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="subject-code">Subject Code</Label>
                  <Input id="subject-code" value={subjectCode} onChange={e => setSubjectCode(e.target.value)} placeholder="e.g. 24CSH-301" className="h-11 bg-muted/50" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="subject-name">Subject Name</Label>
                  <Input id="subject-name" value={subjectName} onChange={e => setSubjectName(e.target.value)} placeholder="e.g. PBLJ" className="h-11 bg-muted/50" />
                </div>
              </CardContent>
            </Card>
          </div>

          <Card className="border-border shadow-sm">
            <CardHeader>
              <CardTitle className="text-2xl">Generate Report</CardTitle>
              <CardDescription className="text-base">Upload your source notes and let AI format the perfect docx.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col items-center justify-center w-full">
                <label htmlFor="dropzone-file" className="flex flex-col items-center justify-center w-full h-56 border-2 border-border border-dashed rounded-xl cursor-pointer bg-muted/30 hover:bg-muted/60 hover:border-primary/50 transition-all group">
                  <div className="flex flex-col items-center justify-center pt-5 pb-6">
                    <div className="h-14 w-14 rounded-full bg-background flex items-center justify-center mb-4 shadow-sm group-hover:scale-110 transition-transform">
                      <Upload className="w-6 h-6 text-primary" />
                    </div>
                    <p className="mb-2 text-sm text-muted-foreground">
                      <span className="font-semibold text-foreground">Click to upload</span> or drag and drop
                    </p>
                    <p className="text-xs text-muted-foreground font-mono bg-background px-2 py-1 rounded-md">{file ? file.name : "Markdown (.md) or Text (.txt)"}</p>
                  </div>
                  <input id="dropzone-file" type="file" className="hidden" accept=".md,.txt" onChange={e => setFile(e.target.files?.[0] || null)} />
                </label>
              </div>
              
              <div className="mt-6 flex items-center justify-center gap-3">
                <input type="checkbox" id="force-refresh" className="w-5 h-5 rounded-md border-input bg-background text-primary focus:ring-primary focus:ring-offset-background" checked={forceRefresh} onChange={e => setForceRefresh(e.target.checked)} />
                <Label htmlFor="force-refresh" className="text-sm font-medium text-muted-foreground cursor-pointer select-none">Force generation (bypass AI cache)</Label>
              </div>
            </CardContent>
            <CardFooter className="pt-2">
              <Button onClick={handleGenerate} disabled={generating || !file} size="lg" className="w-full h-14 text-lg font-semibold rounded-xl transition-all shadow-sm">
                {generating && <Loader2 className="mr-2 h-6 w-6 animate-spin" />}
                {generating ? "Crafting your report..." : "Generate DOCX Report"}
              </Button>
            </CardFooter>
          </Card>
        </main>
        <Toaster />
      </div>
    </ThemeProvider>
  )
}
