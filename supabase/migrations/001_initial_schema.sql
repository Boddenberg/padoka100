create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.products (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text,
  description text,
  visual_description text,
  main_image_url text,
  button_color text,
  sort_order integer not null default 0,
  status text not null default 'active' check (status in ('active', 'inactive')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists products_slug_unique_idx
  on public.products (slug)
  where slug is not null;

drop trigger if exists products_set_updated_at on public.products;
create trigger products_set_updated_at
before update on public.products
for each row execute function public.set_updated_at();

create table if not exists public.product_price_versions (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products(id) on delete cascade,
  sale_price numeric(12, 2) not null check (sale_price >= 0),
  cost_price numeric(12, 2) not null default 0 check (cost_price >= 0),
  currency text not null default 'BRL',
  effective_from date not null,
  effective_to date,
  reason text,
  created_at timestamptz not null default now(),
  check (effective_to is null or effective_to >= effective_from)
);

create unique index if not exists product_price_versions_product_day_idx
  on public.product_price_versions (product_id, effective_from);

create index if not exists product_price_versions_lookup_idx
  on public.product_price_versions (product_id, effective_from desc, effective_to);

create table if not exists public.locations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  address_text text,
  description text,
  main_image_url text,
  status text not null default 'active' check (status in ('active', 'inactive')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists locations_set_updated_at on public.locations;
create trigger locations_set_updated_at
before update on public.locations
for each row execute function public.set_updated_at();

create table if not exists public.sales_days (
  id uuid primary key default gen_random_uuid(),
  business_date date not null,
  location_id uuid references public.locations(id) on delete set null,
  location_name_snapshot text,
  notes text,
  status text not null default 'open' check (status in ('open', 'closed')),
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists sales_days_business_date_idx
  on public.sales_days (business_date desc);

create index if not exists sales_days_status_idx
  on public.sales_days (status);

drop trigger if exists sales_days_set_updated_at on public.sales_days;
create trigger sales_days_set_updated_at
before update on public.sales_days
for each row execute function public.set_updated_at();

create table if not exists public.production_items (
  id uuid primary key default gen_random_uuid(),
  sales_day_id uuid not null references public.sales_days(id) on delete cascade,
  product_id uuid not null references public.products(id) on delete restrict,
  product_name_snapshot text not null,
  product_image_url_snapshot text,
  price_version_id uuid references public.product_price_versions(id) on delete set null,
  unit_sale_price_snapshot numeric(12, 2) not null check (unit_sale_price_snapshot >= 0),
  unit_cost_price_snapshot numeric(12, 2) not null default 0 check (unit_cost_price_snapshot >= 0),
  quantity_produced integer not null check (quantity_produced >= 0),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (sales_day_id, product_id)
);

create index if not exists production_items_sales_day_idx
  on public.production_items (sales_day_id);

drop trigger if exists production_items_set_updated_at on public.production_items;
create trigger production_items_set_updated_at
before update on public.production_items
for each row execute function public.set_updated_at();

create table if not exists public.ai_interactions (
  id uuid primary key default gen_random_uuid(),
  sales_day_id uuid references public.sales_days(id) on delete set null,
  input_type text not null check (input_type in ('text', 'audio')),
  raw_text text,
  audio_url text,
  interpreted_action jsonb,
  confirmation_payload jsonb,
  status text not null default 'interpreted' check (status in ('interpreted', 'confirmed', 'rejected', 'failed')),
  error_message text,
  created_at timestamptz not null default now()
);

create table if not exists public.sales (
  id uuid primary key default gen_random_uuid(),
  sales_day_id uuid not null references public.sales_days(id) on delete cascade,
  input_type text not null default 'manual' check (input_type in ('manual', 'audio', 'ai')),
  ai_interaction_id uuid references public.ai_interactions(id) on delete set null,
  raw_text text,
  audio_url text,
  notes text,
  status text not null default 'active' check (status in ('active', 'voided')),
  occurred_at timestamptz not null default now(),
  voided_at timestamptz,
  void_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists sales_sales_day_idx
  on public.sales (sales_day_id, occurred_at desc);

create index if not exists sales_status_idx
  on public.sales (status);

drop trigger if exists sales_set_updated_at on public.sales;
create trigger sales_set_updated_at
before update on public.sales
for each row execute function public.set_updated_at();

create table if not exists public.sale_items (
  id uuid primary key default gen_random_uuid(),
  sale_id uuid not null references public.sales(id) on delete cascade,
  sales_day_id uuid not null references public.sales_days(id) on delete cascade,
  product_id uuid not null references public.products(id) on delete restrict,
  product_name_snapshot text not null,
  product_image_url_snapshot text,
  price_version_id uuid references public.product_price_versions(id) on delete set null,
  unit_sale_price_snapshot numeric(12, 2) not null check (unit_sale_price_snapshot >= 0),
  unit_cost_price_snapshot numeric(12, 2) not null default 0 check (unit_cost_price_snapshot >= 0),
  quantity integer not null check (quantity > 0),
  total_sale_amount numeric(12, 2) not null check (total_sale_amount >= 0),
  total_cost_amount numeric(12, 2) not null default 0 check (total_cost_amount >= 0),
  created_at timestamptz not null default now()
);

create index if not exists sale_items_sales_day_idx
  on public.sale_items (sales_day_id);

create index if not exists sale_items_product_idx
  on public.sale_items (product_id);

create table if not exists public.media_assets (
  id uuid primary key default gen_random_uuid(),
  owner_type text not null check (owner_type in ('product', 'location', 'sales_day', 'sale', 'ai_interaction')),
  owner_id uuid not null,
  bucket text not null,
  file_path text not null,
  public_url text,
  content_type text,
  description text,
  alt_text text,
  created_at timestamptz not null default now()
);

create index if not exists media_assets_owner_idx
  on public.media_assets (owner_type, owner_id, created_at desc);

create table if not exists public.timeline_events (
  id uuid primary key default gen_random_uuid(),
  sales_day_id uuid references public.sales_days(id) on delete set null,
  entity_type text not null,
  entity_id uuid,
  event_type text not null,
  title text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists timeline_events_sales_day_idx
  on public.timeline_events (sales_day_id, created_at desc);

create index if not exists timeline_events_entity_idx
  on public.timeline_events (entity_type, entity_id, created_at desc);

insert into storage.buckets (id, name, public)
values ('padoka-media', 'padoka-media', true)
on conflict (id) do nothing;
