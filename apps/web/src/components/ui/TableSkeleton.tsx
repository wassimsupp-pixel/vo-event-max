'use client'

import React from 'react'

interface TableSkeletonProps {
  cols: number
  rows?: number
}

export function TableSkeleton({ cols, rows = 3 }: TableSkeletonProps) {
  return (
    <>
      {[...Array(rows)].map((_, rowIndex) => (
        <tr key={rowIndex} className="border-b border-[var(--color-border)] bg-white animate-pulse">
          {[...Array(cols)].map((_, colIndex) => (
            <td key={colIndex} className="p-4">
              <div className="h-4 rounded bg-slate-100" style={{ width: `${35 + Math.random() * 55}%` }} />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}
