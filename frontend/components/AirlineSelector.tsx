"use client";

import React, { useState, useEffect } from "react";
import { getAirlines, Airline } from "@/lib/api";

interface AirlineSelectorProps {
  value: string;
  onChange: (code: string) => void;
  error?: string;
  disabled?: boolean;
}

export function AirlineSelector({
  value,
  onChange,
  error,
  disabled = false,
}: AirlineSelectorProps) {
  const [airlines, setAirlines] = useState<Airline[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    async function fetchAirlines() {
      try {
        const data = await getAirlines();
        setAirlines(data);
      } catch (err) {
        console.error("Failed to fetch airlines:", err);
      }
    }
    fetchAirlines();
  }, []);

  const filteredAirlines = airlines.filter(
    (airline) =>
      airline.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
      airline.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const selectedAirline = airlines.find((a) => a.code === value);

  return (
    <div className="relative">
      <label className="block text-sm font-medium mb-1">
        Select Airline
      </label>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full px-3 py-2 border rounded-md text-left focus:outline-none focus:ring-2 focus:ring-blue-500 ${disabled ? "bg-gray-100 cursor-not-allowed" : "bg-white"
          } ${error ? "border-red-500" : "border-gray-300"}`}
      >
        {selectedAirline ? `${selectedAirline.code} - ${selectedAirline.name}` : "Select an airline..."}
      </button>
      {isOpen && !disabled && (
        <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-md shadow-lg max-h-60 overflow-y-auto">
          <input
            type="text"
            placeholder="Search by code or name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-3 py-2 border-b border-gray-200 focus:outline-none"
          />
          {filteredAirlines.map((airline) => (
            <button
              key={airline.code}
              type="button"
              onClick={() => {
                onChange(airline.code);
                setIsOpen(false);
                setSearchQuery("");
              }}
              className="w-full px-3 py-2 text-left hover:bg-blue-50"
            >
              {airline.code} - {airline.name}
            </button>
          ))}
          {filteredAirlines.length === 0 && (
            <div className="px-3 py-2 text-gray-500">No airlines found</div>
          )}
        </div>
      )}
      {error && <p className="text-red-600 text-sm mt-1">{error}</p>}
    </div>
  );
}
