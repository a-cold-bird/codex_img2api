"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ComponentProps } from "react";
import {
  Ban,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleOff,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  Server,
  Trash2,
  Activity,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  checkAccounts,
  createAccounts,
  deleteAccounts,
  fetchAccounts,
  type Account,
  type AccountStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const accountStatusOptions: { label: string; value: AccountStatus | "all" }[] = [
  { label: "全部状态", value: "all" },
  { label: "正常", value: "正常" },
  { label: "异常", value: "异常" },
  { label: "禁用", value: "禁用" },
];

const statusMeta: Record<
  AccountStatus,
  {
    icon: typeof CheckCircle2;
    badge: ComponentProps<typeof Badge>["variant"];
  }
> = {
  正常: { icon: CheckCircle2, badge: "success" },
  异常: { icon: CircleOff, badge: "danger" },
  禁用: { icon: Ban, badge: "secondary" },
};

const metricCards = [
  { key: "total", label: "上游总数", color: "text-stone-900", icon: Server },
  { key: "active", label: "正常", color: "text-emerald-600", icon: CheckCircle2 },
  { key: "abnormal", label: "异常", color: "text-rose-500", icon: CircleOff },
  { key: "disabled", label: "禁用", color: "text-stone-500", icon: Ban },
] as const;

function formatCompact(value: number) {
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}k`;
  }
  return String(value);
}

export default function AccountsPage() {
  const didLoadRef = useRef(false);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<AccountStatus | "all">("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState("10");
  const [open, setOpen] = useState(false);
  const [newUpstreams, setNewUpstreams] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isChecking, setIsChecking] = useState(false);

  const loadAccounts = async (silent = false) => {
    if (!silent) setIsLoading(true);
    try {
      const data = await fetchAccounts();
      setAccounts(data.items);
      setSelectedIds((prev) => prev.filter((id) => data.items.some((item) => item.id === id)));
    } catch (error) {
      const message = error instanceof Error ? error.message : "加载上游列表失败";
      toast.error(message);
    } finally {
      if (!silent) setIsLoading(false);
    }
  };

  useEffect(() => {
    if (didLoadRef.current) return;
    didLoadRef.current = true;
    void loadAccounts();
  }, []);

  const filteredAccounts = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return accounts.filter((account) => {
      const searchMatched =
        normalizedQuery.length === 0 ||
        account.base_url.toLowerCase().includes(normalizedQuery) ||
        account.api_key_masked.toLowerCase().includes(normalizedQuery);
      const statusMatched = statusFilter === "all" || account.status === statusFilter;
      return searchMatched && statusMatched;
    });
  }, [accounts, query, statusFilter]);

  const pageCount = Math.max(1, Math.ceil(filteredAccounts.length / Number(pageSize)));
  const safePage = Math.min(page, pageCount);
  const startIndex = (safePage - 1) * Number(pageSize);
  const currentRows = filteredAccounts.slice(startIndex, startIndex + Number(pageSize));
  const allCurrentSelected =
    currentRows.length > 0 && currentRows.every((row) => selectedIds.includes(row.id));

  const summary = useMemo(() => {
    const total = accounts.length;
    const active = accounts.filter((item) => item.status === "正常").length;
    const abnormal = accounts.filter((item) => item.status === "异常").length;
    const disabled = accounts.filter((item) => item.status === "禁用").length;
    return { total, active, abnormal, disabled };
  }, [accounts]);

  const selectedKeys = useMemo(() => {
    const selectedSet = new Set(selectedIds);
    return accounts.filter((item) => selectedSet.has(item.id)).map((item) => item.id);
  }, [accounts, selectedIds]);

  const paginationItems = useMemo(() => {
    const items: (number | "...")[] = [];
    const start = Math.max(1, safePage - 1);
    const end = Math.min(pageCount, safePage + 1);
    if (start > 1) items.push(1);
    if (start > 2) items.push("...");
    for (let current = start; current <= end; current += 1) items.push(current);
    if (end < pageCount - 1) items.push("...");
    if (end < pageCount) items.push(pageCount);
    return items;
  }, [pageCount, safePage]);

  const handleAddUpstreams = async () => {
    const lines = newUpstreams
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);

    const upstreams: Array<{ base_url: string; api_key: string }> = [];
    for (const line of lines) {
      const parts = line.split(/[,|\s]+/).filter(Boolean);
      if (parts.length >= 2) {
        const urlPart = parts.find((p) => p.startsWith("http"));
        const keyPart = parts.find((p) => p.startsWith("sk-"));
        if (urlPart && keyPart) {
          upstreams.push({ base_url: urlPart, api_key: keyPart });
          continue;
        }
        upstreams.push({ base_url: parts[0], api_key: parts[1] });
      }
    }

    if (upstreams.length === 0) {
      toast.error("请输入至少一个上游，格式：base_url api_key（每行一个）");
      return;
    }

    setIsSubmitting(true);
    try {
      const data = await createAccounts(upstreams);
      setAccounts(data.items);
      setSelectedIds([]);
      setOpen(false);
      setNewUpstreams("");
      setPage(1);
      toast.success(`新增 ${data.added ?? 0} 个上游`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "新增上游失败";
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteAccounts = async (ids: string[]) => {
    if (ids.length === 0) {
      toast.error("请先选择要删除的上游");
      return;
    }

    setIsDeleting(true);
    try {
      const data = await deleteAccounts(ids);
      setAccounts(data.items);
      setSelectedIds((prev) => prev.filter((id) => data.items.some((item) => item.id === id)));
      toast.success(`删除 ${data.removed ?? 0} 个上游`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "删除上游失败";
      toast.error(message);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleCheckAccounts = async (ids: string[]) => {
    setIsChecking(true);
    try {
      const data = await checkAccounts(ids);
      const results = data.results || [];
      const ok = results.filter((r) => r.status === "正常").length;
      const fail = results.length - ok;
      await loadAccounts(true);
      if (fail === 0) {
        toast.success(`检测完成：${ok} 个上游正常`);
      } else {
        toast.error(`检测完成：${ok} 个正常，${fail} 个异常`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "检测上游失败";
      toast.error(message);
    } finally {
      setIsChecking(false);
    }
  };

  const toggleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds((prev) => Array.from(new Set([...prev, ...currentRows.map((item) => item.id)])));
      return;
    }
    setSelectedIds((prev) => prev.filter((id) => !currentRows.some((row) => row.id === id)));
  };

  return (
    <>
      <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-1">
          <div className="text-xs font-semibold tracking-[0.18em] text-stone-500 uppercase">
            Upstream Pool
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">上游管理</h1>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            className="h-10 rounded-xl border-stone-200 bg-white/80 px-4 text-stone-700 hover:bg-white"
            onClick={() => void loadAccounts()}
            disabled={isLoading || isSubmitting || isDeleting}
          >
            <RefreshCw className={cn("size-4", isLoading ? "animate-spin" : "")} />
            刷新
          </Button>
          <Button
            variant="outline"
            className="h-10 rounded-xl border-stone-200 bg-white/80 px-4 text-stone-700 hover:bg-white"
            onClick={() => void handleCheckAccounts([])}
            disabled={isLoading || isSubmitting || isDeleting || isChecking || accounts.length === 0}
          >
            {isChecking ? <LoaderCircle className="size-4 animate-spin" /> : <Activity className="size-4" />}
            检测全部
          </Button>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="h-10 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800">
                <Plus className="size-4" />
                新增上游
              </Button>
            </DialogTrigger>
            <DialogContent showCloseButton={false} className="rounded-2xl p-6">
              <DialogHeader className="gap-2">
                <DialogTitle>新增上游</DialogTitle>
                <DialogDescription className="text-sm leading-6">
                  每行一个上游，格式：<code className="rounded bg-stone-100 px-1.5 py-0.5 text-xs">base_url api_key</code>
                  <br />
                  例如：<code className="rounded bg-stone-100 px-1.5 py-0.5 text-xs">http://1.2.3.4:8317 sk-xxx</code>
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-stone-700">上游列表</label>
                  <Textarea
                    placeholder={"http://1.2.3.4:8317 sk-xxx\nhttps://api.example.com sk-yyy"}
                    value={newUpstreams}
                    onChange={(event) => setNewUpstreams(event.target.value)}
                    className="min-h-48 resize-none rounded-xl border-stone-200 font-mono text-sm"
                  />
                </div>
              </div>
              <DialogFooter className="pt-2">
                <Button
                  variant="secondary"
                  className="h-10 rounded-xl bg-stone-100 px-5 text-stone-700 hover:bg-stone-200"
                  onClick={() => setOpen(false)}
                  disabled={isSubmitting}
                >
                  取消
                </Button>
                <Button
                  className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
                  onClick={() => void handleAddUpstreams()}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
                  新增
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </section>

      <section className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {metricCards.map((item) => {
            const Icon = item.icon;
            const value = summary[item.key];
            return (
              <Card key={item.key} className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
                <CardContent className="p-4">
                  <div className="mb-4 flex items-start justify-between">
                    <span className="text-xs font-medium text-stone-400">{item.label}</span>
                    <Icon className="size-4 text-stone-400" />
                  </div>
                  <div className={cn("text-[1.75rem] font-semibold tracking-tight", item.color)}>
                    {formatCompact(value)}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold tracking-tight">上游列表</h2>
            <Badge variant="secondary" className="rounded-lg bg-stone-200 px-2 py-0.5 text-stone-700">
              {filteredAccounts.length}
            </Badge>
          </div>

          <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
            <div className="relative min-w-[260px]">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-stone-400" />
              <Input
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setPage(1);
                }}
                placeholder="搜索 URL 或 API Key"
                className="h-10 rounded-xl border-stone-200 bg-white/85 pl-10"
              />
            </div>
            <Select
              value={statusFilter}
              onValueChange={(value) => {
                setStatusFilter(value as AccountStatus | "all");
                setPage(1);
              }}
            >
              <SelectTrigger className="h-10 w-full rounded-xl border-stone-200 bg-white/85 lg:w-[150px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {accountStatusOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {isLoading && accounts.length === 0 ? (
          <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
            <CardContent className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
              <div className="rounded-xl bg-stone-100 p-3 text-stone-500">
                <LoaderCircle className="size-5 animate-spin" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-medium text-stone-700">正在加载</p>
                <p className="text-sm text-stone-500">从后端同步上游列表。</p>
              </div>
            </CardContent>
          </Card>
        ) : null}

        <Card
          className={cn(
            "overflow-hidden rounded-2xl border-white/80 bg-white/90 shadow-sm",
            isLoading && accounts.length === 0 ? "hidden" : "",
          )}
        >
          <CardContent className="space-y-0 p-0">
            <div className="flex flex-col gap-3 border-b border-stone-100 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-wrap items-center gap-2 text-sm text-stone-500">
                <Button
                  variant="ghost"
                  className="h-8 rounded-lg px-3 text-rose-500 hover:bg-rose-50 hover:text-rose-600"
                  onClick={() => void handleDeleteAccounts(selectedKeys)}
                  disabled={selectedKeys.length === 0 || isDeleting}
                >
                  {isDeleting ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
                  删除所选
                </Button>
                <Button
                  variant="ghost"
                  className="h-8 rounded-lg px-3 text-stone-600 hover:bg-stone-50 hover:text-stone-800"
                  onClick={() => void handleCheckAccounts(selectedKeys)}
                  disabled={selectedKeys.length === 0 || isChecking}
                >
                  {isChecking ? <LoaderCircle className="size-4 animate-spin" /> : <Activity className="size-4" />}
                  检测所选
                </Button>
                {selectedIds.length > 0 ? (
                  <span className="rounded-lg bg-stone-100 px-2.5 py-1 text-xs font-medium text-stone-600">
                    已选择 {selectedIds.length} 项
                  </span>
                ) : null}
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left">
                <thead className="border-b border-stone-100 text-[11px] text-stone-400 uppercase tracking-[0.18em]">
                  <tr>
                    <th className="w-12 px-4 py-3">
                      <Checkbox
                        checked={allCurrentSelected}
                        onCheckedChange={(checked) => toggleSelectAll(Boolean(checked))}
                      />
                    </th>
                    <th className="px-4 py-3">上游地址</th>
                    <th className="w-40 px-4 py-3">API Key</th>
                    <th className="w-24 px-4 py-3">状态</th>
                    <th className="w-20 px-4 py-3">成功</th>
                    <th className="w-20 px-4 py-3">失败</th>
                    <th className="w-40 px-4 py-3">上次使用</th>
                    <th className="w-20 px-4 py-3">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {currentRows.map((account) => {
                    const status = statusMeta[account.status] ?? statusMeta["正常"];
                    const StatusIcon = status.icon;

                    return (
                      <tr
                        key={account.id}
                        className="border-b border-stone-100/80 text-sm text-stone-600 transition-colors hover:bg-stone-50/70"
                      >
                        <td className="px-4 py-3">
                          <Checkbox
                            checked={selectedIds.includes(account.id)}
                            onCheckedChange={(checked) => {
                              setSelectedIds((prev) =>
                                checked
                                  ? Array.from(new Set([...prev, account.id]))
                                  : prev.filter((item) => item !== account.id),
                              );
                            }}
                          />
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-sm text-stone-700">{account.base_url}</span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-sm text-stone-500">{account.api_key_masked}</span>
                        </td>
                        <td className="px-4 py-3">
                          <Badge
                            variant={status.badge}
                            className="inline-flex items-center gap-1 rounded-md px-2 py-1"
                          >
                            <StatusIcon className="size-3.5" />
                            {account.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 tabular-nums text-emerald-600">{account.success}</td>
                        <td className="px-4 py-3 tabular-nums text-rose-500">{account.fail}</td>
                        <td className="px-4 py-3 text-xs text-stone-500">
                          {account.last_used_at ?? "—"}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1">
                            <button
                              type="button"
                              className="rounded-lg p-2 text-stone-400 transition hover:bg-stone-50 hover:text-stone-600"
                              onClick={() => void handleCheckAccounts([account.id])}
                              disabled={isChecking}
                            >
                              <Activity className="size-4" />
                            </button>
                            <button
                              type="button"
                              className="rounded-lg p-2 text-stone-400 transition hover:bg-rose-50 hover:text-rose-500"
                              onClick={() => void handleDeleteAccounts([account.id])}
                              disabled={isDeleting}
                            >
                              <Trash2 className="size-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {!isLoading && currentRows.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
                  <div className="rounded-xl bg-stone-100 p-3 text-stone-500">
                    <Search className="size-5" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-stone-700">没有匹配的上游</p>
                    <p className="text-sm text-stone-500">调整筛选条件后重试，或新增上游。</p>
                  </div>
                </div>
              ) : null}
            </div>

            <div className="border-t border-stone-100 px-4 py-4">
              <div className="flex items-center justify-center gap-3 overflow-x-auto whitespace-nowrap">
                <div className="shrink-0 text-sm text-stone-500">
                  显示第 {filteredAccounts.length === 0 ? 0 : startIndex + 1} -{" "}
                  {Math.min(startIndex + Number(pageSize), filteredAccounts.length)} 条，共{" "}
                  {filteredAccounts.length} 条
                </div>

                <span className="shrink-0 text-sm leading-none text-stone-500">
                  {safePage} / {pageCount} 页
                </span>
                <Select
                  value={pageSize}
                  onValueChange={(value) => {
                    setPageSize(value);
                    setPage(1);
                  }}
                >
                  <SelectTrigger className="h-10 w-[108px] shrink-0 rounded-lg border-stone-200 bg-white text-sm leading-none">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="10">10 / 页</SelectItem>
                    <SelectItem value="20">20 / 页</SelectItem>
                    <SelectItem value="50">50 / 页</SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  variant="outline"
                  size="icon"
                  className="size-10 shrink-0 rounded-lg border-stone-200 bg-white"
                  disabled={safePage <= 1}
                  onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                >
                  <ChevronLeft className="size-4" />
                </Button>
                {paginationItems.map((item, index) =>
                  item === "..." ? (
                    <span key={`ellipsis-${index}`} className="px-1 text-sm text-stone-400">
                      ...
                    </span>
                  ) : (
                    <Button
                      key={item}
                      variant={item === safePage ? "default" : "outline"}
                      className={cn(
                        "h-10 min-w-10 shrink-0 rounded-lg px-3",
                        item === safePage
                          ? "bg-stone-950 text-white hover:bg-stone-800"
                          : "border-stone-200 bg-white text-stone-700",
                      )}
                      onClick={() => setPage(item)}
                    >
                      {item}
                    </Button>
                  ),
                )}
                <Button
                  variant="outline"
                  size="icon"
                  className="size-10 shrink-0 rounded-lg border-stone-200 bg-white"
                  disabled={safePage >= pageCount}
                  onClick={() => setPage((prev) => Math.min(pageCount, prev + 1))}
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>
    </>
  );
}
