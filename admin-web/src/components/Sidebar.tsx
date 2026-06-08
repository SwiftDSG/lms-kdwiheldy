"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, FileQuestion } from "lucide-react";

const nav = [
  { href: "/quiz-sets", label: "Quiz Sets", icon: BookOpen },
  { href: "/questions", label: "Questions", icon: FileQuestion },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 min-h-screen bg-white border-r-3 border-brand-600 flex flex-col">
      <div className="p-5 border-b-3 border-brand-600">
        <span className="text-lg font-black text-brand-600">LMS Admin</span>
        <p className="text-xs text-gray-500 mt-0.5 font-medium">CPNS Quiz Platform</p>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-semibold transition-colors ${
                active
                  ? "bg-brand-50 text-brand-600 border-l-3 border-brand-600 pl-2.5"
                  : "text-gray-600 hover:bg-brand-50 hover:text-brand-600"
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
