"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface LeadInfo {
  first_name: string;
  email: string;
  phone: string;
  country: string;
}

interface LeadInfoModalProps {
  onSubmit: (leadInfo: LeadInfo) => void;
}

// Generate random first names
const FIRST_NAMES = [
  "John", "Sarah", "Michael", "Emily", "David", "Jessica", "James", "Amanda",
  "Robert", "Lisa", "William", "Michelle", "Richard", "Ashley", "Joseph", "Jennifer",
  "Thomas", "Melissa", "Christopher", "Nicole", "Daniel", "Stephanie", "Matthew", "Elizabeth"
];

// Generate random countries
const COUNTRIES = [
  "United States", "United Kingdom", "Canada", "Australia", "Germany", "France",
  "Spain", "Italy", "Netherlands", "Sweden", "Norway", "Denmark", "Switzerland",
  "Belgium", "Austria", "Ireland", "Portugal", "Poland", "Greece", "Israel"
];

// Generate random email domains
const EMAIL_DOMAINS = [
  "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
  "protonmail.com", "mail.com", "aol.com", "live.com", "msn.com"
];

function generateRandomLead(): LeadInfo {
  const firstName = FIRST_NAMES[Math.floor(Math.random() * FIRST_NAMES.length)];
  const country = COUNTRIES[Math.floor(Math.random() * COUNTRIES.length)];
  const emailDomain = EMAIL_DOMAINS[Math.floor(Math.random() * EMAIL_DOMAINS.length)];
  const email = `${firstName.toLowerCase()}.${Math.floor(Math.random() * 1000)}@${emailDomain}`;
  
  // Generate random phone number (format: +1-XXX-XXX-XXXX)
  const areaCode = Math.floor(Math.random() * 900) + 100;
  const exchange = Math.floor(Math.random() * 900) + 100;
  const number = Math.floor(Math.random() * 9000) + 1000;
  const phone = `+1-${areaCode}-${exchange}-${number}`;

  return {
    first_name: firstName,
    email,
    phone,
    country,
  };
}

export function LeadInfoModal({ onSubmit }: LeadInfoModalProps) {
  const [leadInfo, setLeadInfo] = useState<LeadInfo>(() => generateRandomLead());
  const [isVisible, setIsVisible] = useState(true);

  // Regenerate lead info on each page load
  useEffect(() => {
    setLeadInfo(generateRandomLead());
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsVisible(false);
    onSubmit(leadInfo);
  };

  if (!isVisible) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <Card className="w-full max-w-md mx-4 shadow-xl">
        <CardHeader>
          <CardTitle className="text-xl">Lead Information</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                First Name
              </label>
              <input
                type="text"
                value={leadInfo.first_name}
                onChange={(e) => setLeadInfo({ ...leadInfo, first_name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Email
              </label>
              <input
                type="email"
                value={leadInfo.email}
                onChange={(e) => setLeadInfo({ ...leadInfo, email: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Phone
              </label>
              <input
                type="tel"
                value={leadInfo.phone}
                onChange={(e) => setLeadInfo({ ...leadInfo, phone: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Country
              </label>
              <input
                type="text"
                value={leadInfo.country}
                onChange={(e) => setLeadInfo({ ...leadInfo, country: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>
            <button
              type="submit"
              className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
            >
              Submit
            </button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
