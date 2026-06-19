import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/",        label: "Chat",    color: "text-purple-400" },
  { to: "/mitre",   label: "MITRE",   color: "text-blue-400"   },
  { to: "/cert",    label: "CERT",    color: "text-orange-400" },
  { to: "/threats", label: "Threats", color: "text-red-400"    },
];

export default function Navbar() {
  return (
    <nav className="bg-gray-900 border-b border-gray-700 px-6 py-3 flex items-center gap-8">
      <span className="text-white font-bold text-lg tracking-tight">
        🛡 CTI Bot
      </span>
      <div className="flex gap-6">
        {LINKS.map(({ to, label, color }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `text-sm font-medium transition-colors ${
                isActive ? `${color} border-b-2 border-current pb-1` : "text-gray-400 hover:text-white"
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
