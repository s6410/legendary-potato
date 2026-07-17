import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { get, send, sendFile } from './client'
import type {
  Account,
  BudgetItem,
  Category,
  CategoryBucket,
  Drift,
  Forecast,
  ImportBatch,
  ImportPreview,
  InspectResult,
  LinkSuggestion,
  Merchant,
  MonthlyReport,
  RecurringSeries,
  Rule,
  SavingsAccount,
  SavingsHistory,
  Summary,
  Target,
  TrendPoint,
  TxnPage,
} from './types'

// ----------------------------------------------------------------- läsning

export const useAccounts = () =>
  useQuery({ queryKey: ['accounts'], queryFn: () => get<Account[]>('/accounts') })

export const useCategories = () =>
  useQuery({ queryKey: ['categories'], queryFn: () => get<Category[]>('/categories') })

export const useTransactions = (params: Record<string, unknown>) =>
  useQuery({
    queryKey: ['transactions', params],
    queryFn: () => get<TxnPage>('/transactions', params),
    placeholderData: (prev) => prev,
  })

export const useSummary = (params: Record<string, unknown>) =>
  useQuery({ queryKey: ['summary', params], queryFn: () => get<Summary>('/insights/summary', params) })

export const useByCategory = (params: Record<string, unknown>) =>
  useQuery({
    queryKey: ['by-category', params],
    queryFn: () => get<CategoryBucket[]>('/insights/by-category', params),
  })

export const useTrend = (params: Record<string, unknown> = {}) =>
  useQuery({ queryKey: ['trend', params], queryFn: () => get<TrendPoint[]>('/insights/trend', params) })

export const useCashflow = (months = 12) =>
  useQuery({
    queryKey: ['cashflow', months],
    queryFn: () => get<TrendPoint[]>('/insights/cashflow', { months }),
  })

export const useTopMerchants = (params: Record<string, unknown>) =>
  useQuery({
    queryKey: ['top-merchants', params],
    queryFn: () => get<Merchant[]>('/insights/top-merchants', params),
  })

export const useRecurring = () =>
  useQuery({ queryKey: ['recurring'], queryFn: () => get<RecurringSeries[]>('/insights/recurring') })

export const useForecast = () =>
  useQuery({ queryKey: ['forecast'], queryFn: () => get<Forecast>('/insights/forecast') })

export const useRules = () => useQuery({ queryKey: ['rules'], queryFn: () => get<Rule[]>('/rules') })

export const useLinkSuggestions = () =>
  useQuery({ queryKey: ['links', 'suggestions'], queryFn: () => get<LinkSuggestion[]>('/links/suggestions') })

export const useConfirmedLinks = () =>
  useQuery({ queryKey: ['links', 'confirmed'], queryFn: () => get<LinkSuggestion[]>('/links/confirmed') })

export const useBatches = () =>
  useQuery({ queryKey: ['batches'], queryFn: () => get<ImportBatch[]>('/import/batches') })

export const useBudgets = (month: string) =>
  useQuery({
    queryKey: ['budgets', month],
    queryFn: () => get<{ month: string; items: BudgetItem[] }>('/budgets', { month }),
  })

export const useSavingsAccounts = () =>
  useQuery({ queryKey: ['savings', 'accounts'], queryFn: () => get<SavingsAccount[]>('/savings/accounts') })

export const useSavingsHistory = () =>
  useQuery({ queryKey: ['savings', 'history'], queryFn: () => get<SavingsHistory>('/savings/history') })

export const useDrift = () =>
  useQuery({ queryKey: ['savings', 'drift'], queryFn: () => get<Drift>('/savings/drift') })

export const useTargets = () =>
  useQuery({ queryKey: ['savings', 'targets'], queryFn: () => get<Target[]>('/savings/targets') })

export const useMonthlyReport = (month: string) =>
  useQuery({
    queryKey: ['report', month],
    queryFn: () => get<MonthlyReport>('/reports/monthly', { month }),
  })

// --------------------------------------------------------------- mutationer

/** Invalidera allt transaktionsberoende efter skrivningar. */
export function useInvalidate() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries()
}

export const useApiMutation = <TArgs, TResult = unknown>(
  fn: (args: TArgs) => Promise<TResult>,
  onSuccess?: (result: TResult) => void,
) => {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: fn,
    onSuccess: (result) => {
      invalidate()
      onSuccess?.(result)
    },
  })
}

export const api = { get, send, sendFile }

export type { ImportPreview, InspectResult }
