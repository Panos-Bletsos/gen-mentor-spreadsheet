# Streamlit to React migration feasibility
_Exported on 2/11/2026 at 21:55:51 GMT+1 from Cursor (2.4.28)_

---

**User**

assess how feasible is to replace streamlit with react. Create a migration plan.

---

**Cursor**

I'll explore the codebase to understand the current Streamlit frontend architecture and assess the feasibility of migrating to React. Let me start by examining the project structure and frontend implementation.

Now let me check the project structure to understand the overall organization and any additional considerations.

Now I have a comprehensive understanding of the project. Let me switch to Plan mode to create a detailed migration plan.

Based on my exploration, here's the comprehensive feasibility assessment and migration plan:

---

# Streamlit to React Migration Assessment

## Feasibility Summary

| Aspect | Feasibility | Risk Level |
|--------|-------------|------------|
| **Overall Migration** | **Feasible** | Medium-High |
| API Integration | Easy | Low |
| State Management | Moderate | Medium |
| UI Components | Moderate | Medium |
| Complex Features | Challenging | High |
| Timeline | Significant | - |

**Verdict**: Migration is technically feasible but requires substantial effort. The backend API is already well-structured for React consumption (RESTful, JSON, CORS-enabled, no auth barriers).

---

## Current Architecture Analysis

### Frontend Scope
- **8 Pages**: Onboarding, Skill Gap, Goal Management, Learning Path, Knowledge Document, Learner Profile, Dashboard, Sheets
- **8 Components**: Chatbot, Goal Refinement, Gap Identification, Navigation, Skill Info, Time Tracking, Topbar, Session Completion
- **7 Utility Modules**: API client, state management, PDF parsing, formatting
- **30+ Session State Keys**: Complex nested state with persistence

### Key Streamlit Dependencies
```
streamlit==1.40.0
streamlit-card, streamlit-chat, streamlit-extras
streamlit-float==0.3.5 (floating chatbot)
st-pages==0.4.5 (navigation)
extra-streamlit-components==0.1.60
plotly (charts)
pdfplumber (PDF extraction)
```

### Complex Features Requiring Careful Migration
1. **Univer Spreadsheet Integration** - Custom HTML/JS iframe
2. **Document Reading Experience** - Section pagination, TOC, auto-scroll
3. **Multi-stage Content Generation** - 4-stage async with progress indicators
4. **Quiz System** - 4 question types with immediate feedback
5. **Floating Chatbot** - Dialog-based with message history
6. **State Persistence** - JSON file-based storage

---

## Migration Plan

### Phase 1: Foundation Setup (Week 1-2)

#### 1.1 Project Scaffolding
```bash
# Recommended stack
npx create-next-app@latest frontend-react --typescript --tailwind --app
cd frontend-react
npm install @tanstack/react-query axios zustand react-hook-form zod
npm install recharts @radix-ui/react-dialog @radix-ui/react-tabs
npm install react-markdown rehype-highlight
```

**Technology Choices**:
| Streamlit Feature | React Equivalent |
|-------------------|------------------|
| `st.session_state` | Zustand + localStorage |
| `st.navigation` | Next.js App Router |
| `st.dialog` | Radix UI Dialog |
| `st.columns/tabs` | Tailwind CSS Grid/Radix Tabs |
| `st.plotly_chart` | Recharts or Plotly.js |
| `httpx` | Axios/fetch + React Query |
| `st.file_uploader` | react-dropzone |
| `st.markdown` | react-markdown |

#### 1.2 API Client Setup
```typescript
// lib/api-client.ts
import axios from 'axios';

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000',
  timeout: 500000, // Match current timeout
});

// Typed API functions for all 25 endpoints
export const apiClient = {
  chatWithTutor: (data: ChatRequest) => api.post('/chat-with-tutor', data),
  refineLearningGoal: (data: GoalRequest) => api.post('/refine-learning-goal', data),
  // ... all 25 endpoints
};
```

#### 1.3 State Management Architecture
```typescript
// stores/app-store.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AppState {
  // Core state (matches PERSIST_KEYS)
  loggedIn: boolean;
  llmType: string;
  goals: Goal[];
  selectedGoalId: string | null;
  learnerInformation: string;
  tutorMessages: Message[];
  documentCaches: Record<string, Document>;
  sessionLearningTimes: Record<string, number>;
  // ... 30+ keys
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // Initial state + actions
    }),
    { name: 'genmentor-storage' }
  )
);
```

---

### Phase 2: Core Pages Migration (Week 3-5)

#### Migration Order (by complexity, dependencies)

| Order | Page | Complexity | Key Challenges |
|-------|------|------------|----------------|
| 1 | Onboarding | Low | Multi-step form, PDF upload |
| 2 | Learner Profile | Low | Display/edit forms |
| 3 | Goal Management | Medium | CRUD, state sync |
| 4 | Skill Gap | Medium | Nested data editing, skill levels |
| 5 | Learning Path | Medium | Session management, progress tracking |
| 6 | Dashboard | Medium | Chart integrations (3 chart types) |
| 7 | Knowledge Document | High | Pagination, TOC, auto-scroll, 4-stage generation |
| 8 | Sheets | High | Univer integration, data parsing |

#### 2.1 Page Structure (Next.js App Router)
```
app/
├── layout.tsx          # Main layout with topbar, sidebar
├── page.tsx            # Redirect to onboarding or dashboard
├── onboarding/
│   └── page.tsx
├── skill-gap/
│   └── page.tsx
├── goals/
│   └── page.tsx
├── learning-path/
│   └── page.tsx
├── document/
│   └── page.tsx
├── profile/
│   └── page.tsx
├── dashboard/
│   └── page.tsx
└── sheets/
    └── page.tsx
```

#### 2.2 Component Library
```
components/
├── ui/                 # Radix primitives + Tailwind
│   ├── button.tsx
│   ├── dialog.tsx
│   ├── tabs.tsx
│   ├── select.tsx
│   └── progress.tsx
├── layout/
│   ├── topbar.tsx
│   ├── sidebar.tsx
│   └── navigation.tsx
├── features/
│   ├── chatbot/
│   ├── skill-gap/
│   ├── goal-refinement/
│   ├── document-viewer/
│   └── quiz/
└── charts/
    ├── radar-chart.tsx
    ├── bar-chart.tsx
    └── line-chart.tsx
```

---

### Phase 3: Complex Feature Migration (Week 6-8)

#### 3.1 Document Reading Experience
**Current**: Section pagination, sidebar TOC, query params, auto-scroll JS

```typescript
// components/features/document-viewer/index.tsx
export function DocumentViewer({ document }: Props) {
  const [currentPage, setCurrentPage] = useState(0);
  const sectionRefs = useRef<Map<string, HTMLElement>>(new Map());
  const router = useRouter();
  const searchParams = useSearchParams();

  // Sync with URL query params
  useEffect(() => {
    const page = searchParams.get('page');
    if (page) setCurrentPage(parseInt(page));
  }, [searchParams]);

  // Auto-scroll to anchor
  const scrollToSection = (anchor: string) => {
    sectionRefs.current.get(anchor)?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="flex">
      <TableOfContents sections={document.sections} onNavigate={scrollToSection} />
      <DocumentContent 
        section={document.sections[currentPage]}
        onPrevious={() => setCurrentPage(p => Math.max(0, p - 1))}
        onNext={() => setCurrentPage(p => Math.min(document.sections.length - 1, p + 1))}
      />
    </div>
  );
}
```

#### 3.2 Multi-Stage Content Generation
**Current**: 4 async stages with spinners and progress

```typescript
// hooks/use-content-generation.ts
export function useContentGeneration() {
  const [stage, setStage] = useState<'idle' | 'exploring' | 'drafting' | 'integrating' | 'quiz'>('idle');
  const [progress, setProgress] = useState(0);

  const generateContent = async (session: Session) => {
    try {
      setStage('exploring');
      setProgress(25);
      const points = await apiClient.exploreKnowledgePoints(session);

      setStage('drafting');
      setProgress(50);
      const drafts = await apiClient.draftKnowledgePoints(points);

      setStage('integrating');
      setProgress(75);
      const document = await apiClient.integrateLearningDocument(drafts);

      setStage('quiz');
      setProgress(100);
      const quizzes = await apiClient.generateDocumentQuizzes(document);

      return { document, quizzes };
    } finally {
      setStage('idle');
    }
  };

  return { stage, progress, generateContent };
}
```

#### 3.3 Univer Spreadsheet Integration
**Current**: Custom HTML/JS iframe in `components.html()`

```typescript
// components/features/sheets/univer-sheet.tsx
export function UniverSheet({ onDataChange }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    // Message listener for sheet data
    const handleMessage = (event: MessageEvent) => {
      if (event.data.type === 'SHEET_DATA_UPDATE') {
        onDataChange(event.data.payload);
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [onDataChange]);

  return (
    <iframe
      ref={iframeRef}
      src="/univer/index.html"
      className="w-full h-[600px] border rounded"
    />
  );
}
```

#### 3.4 Floating Chatbot
**Current**: `streamlit-float` + `st.dialog`

```typescript
// components/features/chatbot/floating-chatbot.tsx
export function FloatingChatbot() {
  const [isOpen, setIsOpen] = useState(false);
  const { messages, sendMessage } = useChatbot();

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 w-14 h-14 rounded-full bg-blue-600 shadow-lg"
      >
        <ChatIcon />
      </button>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="fixed bottom-24 right-6 w-96 h-[500px]">
          <ChatInterface messages={messages} onSend={sendMessage} />
        </DialogContent>
      </Dialog>
    </>
  );
}
```

#### 3.5 PDF Upload & Parsing
**Challenge**: `pdfplumber` is Python-only

**Options**:
1. **Backend endpoint** (Recommended): Add `/parse-pdf` endpoint to backend
2. **Client-side**: Use `pdf.js` or `pdf-parse` (WASM)

```typescript
// Option 1: Backend parsing
const uploadPDF = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post('/parse-pdf', formData);
  return data.text;
};
```

---

### Phase 4: Testing & Refinement (Week 9-10)

#### 4.1 Testing Strategy
- **Unit Tests**: Jest + React Testing Library for components
- **Integration Tests**: API client with MSW (Mock Service Worker)
- **E2E Tests**: Playwright for critical user flows

#### 4.2 Feature Parity Checklist
- [ ] All 8 pages functional
- [ ] State persistence works (localStorage)
- [ ] All 25 API endpoints integrated
- [ ] Charts display correctly
- [ ] PDF upload works
- [ ] Univer sheets integration
- [ ] Chatbot with history
- [ ] Quiz system with 4 question types
- [ ] Document pagination and TOC
- [ ] Time tracking
- [ ] Multi-stage content generation with progress

---

## Risk Assessment & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Univer integration complexity | High | Medium | Keep existing HTML/JS, embed via iframe |
| State migration data loss | High | Low | Export/import migration tool |
| Long API timeouts (500s) | Medium | Medium | Use React Query with proper timeout config |
| PDF parsing on client | Medium | Low | Add backend endpoint |
| Chart library differences | Low | Medium | Use Plotly.js for exact parity, or Recharts |
| Learning curve for team | Medium | Varies | Depends on team React experience |

---

## Backend Changes Required

1. **Add PDF parsing endpoint** (if client-side not viable):
```python
@app.post("/parse-pdf")
async def parse_pdf(file: UploadFile):
    import pdfplumber
    text = ""
    with pdfplumber.open(file.file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return {"text": text}
```

2. **No other backend changes required** - API is already React-ready

---

## Recommended Technology Stack

| Category | Technology | Rationale |
|----------|------------|-----------|
| Framework | Next.js 14 (App Router) | File-based routing, SSR/SSG options, excellent DX |
| Styling | Tailwind CSS | Rapid development, consistent design system |
| State | Zustand + React Query | Simple global state + server state caching |
| UI Components | Radix UI + shadcn/ui | Accessible, unstyled primitives |
| Forms | React Hook Form + Zod | Type-safe validation |
| Charts | Recharts or Plotly.js | Interactive visualizations |
| HTTP Client | Axios | Familiar API, interceptors |
| PDF | Backend endpoint | Simplest approach |

---

## Effort Estimation

| Phase | Effort | Key Deliverables |
|-------|--------|------------------|
| Phase 1: Foundation | 1-2 weeks | Project setup, API client, state management |
| Phase 2: Core Pages | 2-3 weeks | 8 pages migrated |
| Phase 3: Complex Features | 2-3 weeks | Document viewer, sheets, chatbot, quizzes |
| Phase 4: Testing | 1-2 weeks | Tests, bug fixes, polish |
| **Total** | **6-10 weeks** | Full feature parity |

---

## Recommendation

**Proceed with migration if**:
- Team has React/Next.js experience
- Need better performance, customization, or ecosystem
- Planning significant new features that Streamlit limits

**Stay with Streamlit if**:
- Rapid prototyping is priority
- Small team without frontend specialists
- Current UI meets all requirements
- Limited development resources

The migration is feasible and the backend is already well-suited for React. The main effort is in recreating the Streamlit-specific UI patterns and the complex features like the document reader and Univer integration.

