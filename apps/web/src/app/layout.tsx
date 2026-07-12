import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'VO Event Max',
  description: 'Plateforme de gestion événementielle',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
