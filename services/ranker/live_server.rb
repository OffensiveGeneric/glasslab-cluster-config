#!/usr/bin/env ruby
# frozen_string_literal: true

require 'json'
require 'webrick'

TOKEN_RE = /[a-z0-9]+/

WORKFLOW_HINTS = {
  'literature-to-experiment' => %w[paper literature claim method study review],
  'generic-tabular-benchmark' => %w[tabular benchmark dataset csv train test titanic],
  'replication-lite' => %w[replicate replication reproduce repeat rerun]
}.freeze

def tokenize(value)
  value.to_s.downcase.scan(TOKEN_RE)
end

def counts(tokens)
  tokens.each_with_object(Hash.new(0)) do |token, acc|
    acc[token] += 1
  end
end

def score_candidate(query, workflow_id, summary, hints)
  query_tokens = tokenize(query)
  summary_tokens = tokenize(summary)

  query_counts = counts(query_tokens)
  summary_counts = counts(summary_tokens)

  overlap = query_counts.sum do |token, count|
    [count, summary_counts.fetch(token, 0)].min
  end.to_f

  hint_score = 0.0
  matched_hints = []
  WORKFLOW_HINTS.fetch(workflow_id, []).each do |token|
    next unless query_counts.key?(token)

    hint_score += 1.0
    matched_hints << token
  end

  metadata_bonus = 0.0
  dataset_hint = hints['dataset_name']
  if workflow_id == 'generic-tabular-benchmark' && dataset_hint.is_a?(String) && !dataset_hint.strip.empty?
    metadata_bonus += 1.0
  end

  source_type = hints['source_type']
  if workflow_id == 'literature-to-experiment' && source_type == 'paper-link'
    metadata_bonus += 1.0
  end

  score = overlap + hint_score + metadata_bonus
  reasons = []
  reasons << "query/summary token overlap=#{overlap.to_i}" if overlap.positive?
  reasons << "matched workflow hints: #{matched_hints.sort.join(', ')}" unless matched_hints.empty?
  reasons << format('backend hints bonus=%.1f', metadata_bonus) if metadata_bonus.positive?
  reasons << 'no strong lexical match; kept as low-confidence fallback' if reasons.empty?

  [score, reasons.join('; ')]
end

def json_response(res, status_code, payload)
  res.status = status_code
  res['Content-Type'] = 'application/json'
  res.body = JSON.generate(payload)
end

server = WEBrick::HTTPServer.new(
  Port: Integer(ENV.fetch('GLASSLAB_RANKER_PORT', '8181')),
  BindAddress: ENV.fetch('GLASSLAB_RANKER_BIND', '0.0.0.0'),
  AccessLog: [],
  Logger: WEBrick::Log.new($stderr, WEBrick::Log::INFO)
)

server.mount_proc '/healthz' do |_req, res|
  json_response(res, 200, { status: 'ok' })
end

server.mount_proc '/rank/workflow-family' do |req, res|
  unless req.request_method == 'POST'
    json_response(res, 405, { error: 'method not allowed' })
    next
  end

  begin
    payload = JSON.parse(req.body)
    request_id = payload.fetch('request_id')
    query = payload.fetch('query')
    candidates = payload.fetch('candidates')
    hints = payload.fetch('hints', {})

    ranked = candidates.map do |candidate|
      workflow_id = candidate.fetch('workflow_id')
      summary = candidate.fetch('summary')
      score, reason = score_candidate(query, workflow_id, summary, hints)
      {
        workflow_id: workflow_id,
        score: score,
        reason: reason
      }
    end

    ranked.sort_by! { |item| [-item[:score], item[:workflow_id]] }

    json_response(res, 200, {
      request_id: request_id,
      ranked_candidates: ranked,
      ranking_basis: 'deterministic lexical overlap plus workflow-specific hint bonuses'
    })
  rescue KeyError => e
    json_response(res, 400, { error: "missing required field: #{e.key}" })
  rescue JSON::ParserError
    json_response(res, 400, { error: 'invalid json' })
  rescue StandardError => e
    warn "[ranker] #{e.class}: #{e.message}"
    e.backtrace&.each { |line| warn "[ranker] #{line}" }
    json_response(res, 500, { error: e.message })
  end
end

trap('INT') { server.shutdown }
trap('TERM') { server.shutdown }

server.start
