"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { LoaderCircle, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fetchGeneratedImagesHistory, type GeneratedImageHistoryItem } from "@/lib/api";


function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export default function HistoryPage() {
  const [items, setItems] = useState<GeneratedImageHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async (silent = false) => {
      if (!silent) {
        setIsLoading(true);
      }
      try {
        const data = await fetchGeneratedImagesHistory();
        if (!cancelled) {
          setItems(data.items || []);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "读取历史图片失败";
        toast.error(message);
      } finally {
        if (!cancelled && !silent) {
          setIsLoading(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="text-xs font-semibold tracking-[0.18em] text-stone-500 uppercase">Image History</div>
          <h1 className="text-2xl font-semibold tracking-tight">历史图片</h1>
        </div>
        <Button
          variant="outline"
          className="h-10 rounded-xl border-stone-200 bg-white/85 px-4 text-stone-700 hover:bg-white"
          onClick={() => void (async () => {
            try {
              const data = await fetchGeneratedImagesHistory();
              setItems(data.items || []);
              toast.success("历史记录已刷新");
            } catch (error) {
              const message = error instanceof Error ? error.message : "刷新历史记录失败";
              toast.error(message);
            }
          })()}
        >
          <RefreshCw className="size-4" />
          刷新
        </Button>
      </div>

      {isLoading ? (
        <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
          <CardContent className="flex items-center gap-3 p-6 text-sm text-stone-500">
            <LoaderCircle className="size-4 animate-spin" />
            正在读取服务端历史图片
          </CardContent>
        </Card>
      ) : null}

      {!isLoading && items.length === 0 ? (
        <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
          <CardContent className="p-6 text-sm text-stone-500">暂无服务端落盘图片。</CardContent>
        </Card>
      ) : null}

      {items.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => (
            <Card key={item.image_id} className="overflow-hidden rounded-2xl border-white/80 bg-white/90 shadow-sm">
              <div className="relative aspect-[4/5] bg-stone-100">
                <Image src={item.url} alt={item.prompt || item.image_id} fill unoptimized className="object-cover" />
              </div>
              <CardContent className="space-y-3 p-4">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="secondary">{item.requested_model || "unknown"}</Badge>
                  <Badge variant="info">{Math.round((item.size_bytes || 0) / 1024)} KB</Badge>
                </div>
                <div className="text-sm leading-6 text-stone-700" title={item.prompt || item.revised_prompt || "—"}>
                  {item.prompt || item.revised_prompt || "—"}
                </div>
                <div className="space-y-1 text-xs text-stone-500">
                  <div>创建：{formatDate(item.created_at)}</div>
                  <div>过期：{formatDate(item.expires_at)}</div>
                  <div className="truncate">ID：{item.image_id}</div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </section>
  );
}
