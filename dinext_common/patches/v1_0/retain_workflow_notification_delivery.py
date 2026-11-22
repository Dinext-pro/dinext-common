def execute():
	from dinext_common.workflow_approval.projections import backfill_delivery_snapshots

	backfill_delivery_snapshots()
