export type Category = "TWK" | "TIU" | "TKP" | "MIXED";
export type QuestionType = "MCQ" | "TRUE_FALSE" | "ESSAY" | "IMAGE";

export type TwkSubtype =
  | "PANCASILA" | "UUD_1945" | "BHINNEKA" | "NKRI"
  | "SEJARAH_NASIONAL" | "SISTEM_PEMERINTAHAN" | "BELA_NEGARA" | "BAHASA_INDONESIA";

export type TiuSubtype =
  | "ANALOGI_VERBAL" | "ANALOGI_GAMBAR" | "SILOGISME" | "ANTONIM" | "SINONIM"
  | "ARITMATIKA" | "DERET_ANGKA" | "SOAL_CERITA" | "PERBANDINGAN_KUANTITATIF";

export type TkpSubtype =
  | "PELAYANAN_PUBLIK" | "PROFESIONALISME" | "JEJARING_KERJA" | "SOSIAL_BUDAYA"
  | "TEKNOLOGI_INFORMASI" | "ORIENTASI_BELAJAR" | "MENGENDALIKAN_DIRI"
  | "BERADAPTASI" | "KREATIVITAS_INOVASI";

export type QuestionSubtype = TwkSubtype | TiuSubtype | TkpSubtype;

export interface Quiz {
  id: string;
  title: string;
  description: string | null;
  category: Category;
  time_limit: number | null;
  is_published: boolean;
  created_at: string;
  updated_at: string;
}

export interface QuestionOption {
  id: string;
  question_id: string;
  label: string;
  content: string;
  score: number;
}

export interface Question {
  id: string;
  quiz_id: string;
  type: QuestionType;
  subtype: QuestionSubtype;
  content: string;
  image_url: string | null;
  explanation: string | null;
  position: number;
  created_at: string;
  options: QuestionOption[];
}

export interface QuizSession {
  id: string;
  quiz_id: string;
  device_id: string;
  started_at: string;
  completed_at: string | null;
  score: number | null;
  synced_at: string;
}

// ── AI generation types ───────────────────────────────────────────────────────

export interface GeneratedOption {
  label:   string;
  content: string;
  score:   number;
}

export interface GeneratedQuestion {
  content:     string;
  image_url?:  string;  // set for ANALOGI_GAMBAR
  options:     GeneratedOption[];
  explanation: string;
  tip?:        string;
}

// ── Form types ────────────────────────────────────────────────────────────────

export interface CreateQuizForm {
  title: string;
  description?: string;
  category: Category;
  time_limit?: number;
}

export interface CreateOptionForm {
  label: string;
  content: string;
  score: number;
}

export interface CreateQuestionForm {
  quiz_id: string;
  type: QuestionType;
  subtype: QuestionSubtype;
  content: string;
  image_url?: string;
  explanation?: string;
  position: number;
  options?: CreateOptionForm[];
}
