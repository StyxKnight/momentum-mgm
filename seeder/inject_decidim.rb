# Momentum MGM — Decidim Society Injector
# Rails runner: injects 20 citizens, 40 proposals, 60 comments, 6 meetings
# Run: ~/.rbenv/shims/rails runner /home/styxknight/momentum-mgm/seeder/inject_decidim.rb

require 'json'

DATA = JSON.parse(File.read('/tmp/society_content.json'))
ORG  = Decidim::Organization.first

# ── Category → Proposals component ID mapping ────────────────────────────────
PROPOSALS_COMPONENT = {
  'housing'       => 30,
  'public_safety' => 31,
  'transportation'=> 32,
  'health'        => 33,
  'education'     => 34,
  'economy'       => 35,
  'governance'    => 37,
  'environment'   => 29,
  'infrastructure'=> 28,
  'parks_culture' => 36,
}

MEETINGS_COMPONENT = {
  'housing'       => 43,
  'public_safety' => 45,
  'transportation'=> 47,
  'health'        => 49,
  'education'     => 51,
  'economy'       => 53,
  'governance'    => 57,
  'environment'   => 41,
  'infrastructure'=> 39,
  'parks_culture' => 55,
}

puts "=== Momentum MGM Society Injection ==="
puts "  #{DATA['characters'].length} citizens | #{DATA['proposals'].length} proposals | #{DATA['comments'].length} comments | #{DATA['meetings'].length} meetings"

# ── Step 1: Create citizen users ─────────────────────────────────────────────
puts "\n── Step 1: Creating citizens..."
user_map = {}  # character_id => Decidim::User

DATA['characters'].each do |c|
  email    = c['email']
  username = c['username']
  name     = "#{c['first_name']} #{c['last_name']}"

  user = Decidim::User.find_by(email: email)
  if user
    puts "  SKIP #{name} (already exists)"
  else
    # Decidim nicknames: only letters, numbers, underscores, hyphens
    nickname = "#{c['first_name']}_#{c['last_name']}".downcase.gsub(/[^a-z0-9_]/, '')[0..19]

    user = Decidim::User.new(
      organization:          ORG,
      email:                 email,
      name:                  name,
      nickname:              nickname,
      password:              c['password'],
      password_confirmation: c['password'],
      locale:                'en',
      tos_agreement:         true,
      accepted_tos_version:  ORG.tos_version,
    )
    user.skip_reconfirmation!
    if user.save
      user.update_columns(confirmed_at: Time.current)
      puts "  ✓ #{name} (#{c['neighborhood']}, #{c['profession']})"
    else
      puts "  ✗ #{name}: #{user.errors.full_messages.join(', ')}"
    end
  end
  user_map[c['id']] = Decidim::User.find_by(email: email)
end

puts "  Created/found #{user_map.values.compact.length}/#{DATA['characters'].length} users"

# ── Step 2: Post proposals ───────────────────────────────────────────────────
puts "\n── Step 2: Posting proposals..."
proposal_map = {}  # proposal array index => Decidim::Proposals::Proposal

DATA['proposals'].each_with_index do |p, idx|
  author    = user_map[p['character_id']]
  unless author
    puts "  ✗ Proposal #{idx}: author #{p['character_id']} not found"
    next
  end

  comp_id = PROPOSALS_COMPONENT[p['category']]
  unless comp_id
    puts "  ✗ Proposal #{idx}: unknown category #{p['category']}"
    next
  end

  component = Decidim::Component.find_by(id: comp_id)
  unless component
    puts "  ✗ Component #{comp_id} not found"
    next
  end

  proposal = Decidim::Proposals::Proposal.new(
    component:    component,
    title:        { 'en' => p['title'] },
    body:         { 'en' => p['body'] },
    published_at: Time.current - rand(1..72).hours,
  )
  proposal.add_coauthor(author)

  if proposal.save
    proposal_map[idx] = proposal
    print "  ✓"
  else
    puts "  ✗ [#{idx}] #{p['title'][0..50]}: #{proposal.errors.full_messages.first}"
  end
end
puts "\n  #{proposal_map.length}/#{DATA['proposals'].length} proposals posted"

# ── Step 3: Post comments ────────────────────────────────────────────────────
puts "\n── Step 3: Posting comments..."
comment_ok = 0
comment_fail = 0

DATA['comments'].each do |c|
  author   = user_map[c['commenter_id']]
  proposal = proposal_map[c['proposal_idx']]

  unless author && proposal
    comment_fail += 1
    next
  end

  alignment = c['alignment'].to_i  # 1, 0, -1

  comment = Decidim::Comments::Comment.new(
    author:       author,
    commentable:  proposal,
    root_commentable: proposal,
    body:         { 'en' => c['body'] },
    alignment:    alignment,
  )

  if comment.save
    comment_ok += 1
    print "."
  else
    comment_fail += 1
  end
end
puts "\n  #{comment_ok} comments posted, #{comment_fail} failed"

# ── Step 4: Schedule meetings ────────────────────────────────────────────────
puts "\n── Step 4: Scheduling meetings..."
admin = Decidim::User.find_by(email: 'admin@mgm.styxcore.dev') ||
        Decidim::User.where(admin: true).first

meeting_ok = 0
DATA['meetings'].each do |m|
  # Pick component: first meeting from type mapping, fallback to governance
  cat = case m['type']
        when 'council'      then 'governance'
        when 'hearing'      then 'infrastructure'
        when 'forum'        then 'housing'
        when 'committee'    then 'transportation'
        when 'consultation' then 'parks_culture'
        else 'governance'
        end
  comp_id   = MEETINGS_COMPONENT[cat]
  component = Decidim::Component.find_by(id: comp_id)
  next unless component

  start_t = Time.parse(m['start_time']) rescue (Time.current + 14.days)
  end_t   = Time.parse(m['end_time'])   rescue (start_t + 2.hours)

  meeting = Decidim::Meetings::Meeting.new(
    component:    component,
    title:        { 'en' => m['title'] },
    description:  { 'en' => m['description'] },
    start_time:   start_t,
    end_time:     end_t,
    address:      m['address'] || 'Montgomery, AL',
    location:     { 'en' => m['location'] || m['title'] },
    location_hints: { 'en' => '' },
    author:       admin,
    published_at: Time.current,
    registration_type: 'registration_disabled',
    attendees_count: 0,
  )

  if meeting.save
    meeting_ok += 1
    puts "  ✓ #{m['start_time'][0..9]} — #{m['title'][0..60]}"
  else
    puts "  ✗ #{m['title'][0..50]}: #{meeting.errors.full_messages.first}"
  end
end
puts "  #{meeting_ok}/#{DATA['meetings'].length} meetings scheduled"

# ── Done ─────────────────────────────────────────────────────────────────────
puts "\n=== Injection complete ==="
puts "  Users:     #{user_map.values.compact.length}"
puts "  Proposals: #{proposal_map.length}"
puts "  Comments:  #{comment_ok}"
puts "  Meetings:  #{meeting_ok}"
puts "\n  Platform: https://mgm.styxcore.dev"
