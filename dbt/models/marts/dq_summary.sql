-- Gold: what the pipeline caught. One row per data-quality measure, shown in the app.
-- "stage" says where the problem was handled: at ingest (rejected to the dead-letter
-- queue) or in silver (cleaned by a dbt model).

with bronze_events as (

    select * from {{ source('bronze', 'events') }}

),

dead_letter as (

    select * from {{ source('bronze', 'dead_letter') }}

),

silver_events as (

    select * from {{ ref('stg_events') }}

),

measures as (

    select
        1 as sort_order, 'ingest' as stage, 'event_lines_received' as measure,
        (select count(*) from bronze_events) + (select count(*) from dead_letter) as row_count,
        'Event lines read from the landing files' as description

    union all

    select
        2, 'ingest', 'rejected_' || reason, count(*),
        'Rejected at ingest and sent to the dead-letter queue'
    from dead_letter
    group by reason

    union all

    select
        3, 'ingest', 'events_loaded_to_bronze', count(*),
        'Events that passed schema validation'
    from bronze_events

    union all

    select
        4, 'silver', 'duplicate_events_removed', count(*) - count(distinct event_id),
        'Second deliveries of an event already loaded'
    from bronze_events

    union all

    select
        5, 'silver', 'future_dated_events_removed', count(distinct event_id),
        'Events dated after today (a device with a wrong clock)'
    from bronze_events
    where cast(occurred_at as date) > {{ as_of_date() }}

    union all

    select
        6, 'silver', 'late_arriving_events_kept', count(*),
        'Events that arrived in the file of a later day; kept under their true date'
    from silver_events
    where _source_file not like 'backfill%'
      and event_date < cast(left(_source_file, 10) as date)

    union all

    select
        7, 'silver', 'events_in_silver', count(*),
        'Clean events available to the gold tables'
    from silver_events

    union all

    select
        8, 'silver', 'duplicate_contacts_removed',
        (select count(*) from {{ source('bronze', 'crm_contacts') }})
            - (select count(*) from {{ ref('stg_contacts') }}),
        'The same person entered twice on one account'

    union all

    select
        9, 'silver', 'persona_tags_normalised', count(*),
        'Contacts whose persona was written in a non-standard way'
    from {{ ref('stg_contacts') }}
    where persona_raw <> persona

)

select * from measures
order by sort_order, measure
