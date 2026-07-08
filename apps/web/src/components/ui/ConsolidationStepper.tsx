'use client'

import { useTranslations } from 'next-intl'
import { Check, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Step {
  label: string
  count?: string
  status: 'done' | 'active' | 'pending'
}

interface ConsolidationStepperProps {
  steps?: Step[]
  className?: string
}

const defaultStepKeys = ['import', 'analysis', 'matching', 'consolidation', 'validation'] as const

export function ConsolidationStepper({ steps, className }: ConsolidationStepperProps) {
  const t = useTranslations('steps')

  const resolvedSteps: Step[] = steps ?? [
    { label: t('import'), status: 'done', count: '7 sources' },
    { label: t('analysis'), status: 'done', count: '324 lignes' },
    { label: t('matching'), status: 'done', count: '98.2% match' },
    { label: t('consolidation'), status: 'active', count: 'En cours...' },
    { label: t('validation'), status: 'pending' },
  ]

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      {resolvedSteps.map((step, index) => (
        <div key={index} className="flex items-start gap-3">
          {/* Step indicator column */}
          <div className="flex flex-col items-center">
            {/* Circle */}
            <div
              className={cn(
                'flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-xs font-bold transition-all',
                step.status === 'done' &&
                  'bg-[var(--color-success)] text-white',
                step.status === 'active' &&
                  'bg-[var(--color-cta)] text-white shadow-md',
                step.status === 'pending' &&
                  'border-2 border-[var(--color-border-strong)] bg-white text-[var(--color-text-secondary)]'
              )}
            >
              {step.status === 'done' && <Check className="h-3.5 w-3.5" />}
              {step.status === 'active' && (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              )}
              {step.status === 'pending' && (
                <span>{index + 1}</span>
              )}
            </div>

            {/* Connector line */}
            {index < resolvedSteps.length - 1 && (
              <div
                className={cn(
                  'mt-1 w-0.5 flex-1 min-h-[16px]',
                  step.status === 'done'
                    ? 'bg-[var(--color-success)]'
                    : 'bg-[var(--color-border-strong)]'
                )}
              />
            )}
          </div>

          {/* Label + count */}
          <div className="pb-3">
            <p
              className={cn(
                'text-sm font-semibold leading-tight',
                step.status === 'done' && 'text-[var(--color-success)]',
                step.status === 'active' && 'text-[var(--color-cta)]',
                step.status === 'pending' && 'text-[var(--color-text-secondary)]'
              )}
            >
              {step.label}
            </p>
            {step.count && (
              <p className="mt-0.5 text-xs text-[var(--color-text-secondary)]">{step.count}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
