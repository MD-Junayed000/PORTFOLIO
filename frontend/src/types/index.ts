export interface About {
  id: number;
  bio: string;
  title: string;
  photo_url: string | null;
  education: string | null;
  focus_area: string | null;
  subtitle: string | null;
  linkedin_url: string | null;
  github_url: string | null;
  scholar_url: string | null;
  extra_links: string | null; // JSON string of [{name, url, icon}]
  cv_file_path: string | null;
}

export interface ExtraLink {
  name: string;
  url: string;
  icon?: string;
}

export interface ContactInfo {
  id: number;
  email: string | null;
  phone: string | null;
  address: string | null;
  notification_emails: string | null;
}

export interface Project {
  id: number;
  name: string;
  description: string;
  tech_stack: string;
  repo_url: string | null;
  demo_url: string | null;
  image_url: string | null;
  order: number;
}

export interface Skill {
  id: number;
  category: string;
  name: string;
  proficiency: number;
}

export interface Research {
  id: number;
  title: string;
  venue: string | null;
  year: number | null;
  status: string;
  link: string | null;
}

export interface Certificate {
  id: number;
  name: string;
  issuer: string;
  date: string;
  file_path: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
}

export interface ChatResponse {
  response: string;
  sources: string[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface Experience {
  id: number;
  title: string;
  organization: string;
  period: string;
  description: string | null;
  logo_url: string | null;
  order: number;
}

export interface Document {
  id: number;
  filename: string;
  topic: string | null;
  original_name: string | null;
  uploaded_at: string;
  chunk_count: number | null;
}

export interface ContactMessage {
  id: number;
  name: string;
  email: string;
  message: string;
  created_at: string;
}

export interface DatabaseInfo {
  name: string;
  row_count: number;
}
