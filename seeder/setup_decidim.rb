require 'json'

puts "=== Momentum MGM — Decidim Setup ==="

org = Decidim::Organization.first
admin = Decidim::User.find_by(email: "admin@mgm.styxcore.dev")

# ── 1. Supprimer le process lorem ipsum (id=1) ─────────────────────────────
puts "\n[1] Suppression process lorem ipsum (id=1)..."
process = Decidim::ParticipatoryProcess.find_by(id: 1)
if process
  # Supprimer composants et leur contenu
  process.components.each do |comp|
    comp.destroy!
  end
  process.destroy!
  puts "  ✓ Process 'trivial-turkey' supprimé"
else
  puts "  ℹ️  Process id=1 déjà supprimé"
end

# ── 2. Contenu civique généré par Grok-4 ───────────────────────────────────
CONTENT = {
  "infrastructure" => {
    debates: [
      { title: "Improving Road Maintenance in Montgomery Neighborhoods",
        description: "<p>Discuss strategies for prioritizing road repairs and pothole fixes in residential areas to enhance safety and accessibility for all residents.</p>" },
      { title: "Upgrading Water and Sewer Systems for Future Growth",
        description: "<p>Explore solutions to modernize Montgomery's aging water infrastructure to prevent leaks and ensure reliable service amid population growth.</p>" }
    ],
    meetings: [
      { title: "Public Hearing on Bridge Replacement Projects",
        description: "<p>Join engineers and city officials to review plans for replacing outdated bridges and gather community input on traffic impacts.</p>",
        location: "Montgomery City Hall" },
      { title: "Community Workshop on Utility Upgrades",
        description: "<p>Participate in discussions about upcoming utility improvements and share ideas for minimizing disruptions during construction.</p>",
        location: "Cleveland Avenue YMCA" }
    ]
  },
  "environment" => {
    debates: [
      { title: "Reducing Air Pollution from Industrial Sources",
        description: "<p>Debate effective measures to monitor and decrease emissions from local industries while supporting economic development in Montgomery.</p>" },
      { title: "Protecting the Alabama River Ecosystem",
        description: "<p>Discuss community-led initiatives to preserve water quality and wildlife habitats along the Alabama River for sustainable environmental health.</p>" }
    ],
    meetings: [
      { title: "Town Hall on Urban Green Spaces Expansion",
        description: "<p>Engage with environmental experts to plan for more green areas and tree-planting programs to combat urban heat in Montgomery.</p>",
        location: "Montgomery Public Library - Main Branch" },
      { title: "Public Session on Recycling Program Enhancements",
        description: "<p>Review proposals to improve city-wide recycling efforts and provide feedback on waste reduction strategies.</p>",
        location: "Alabama State Capitol" }
    ]
  },
  "housing" => {
    debates: [
      { title: "Addressing Affordable Housing Shortages",
        description: "<p>Explore policies to increase affordable housing options and support low-income families in Montgomery's diverse neighborhoods.</p>" },
      { title: "Promoting Sustainable Home Development",
        description: "<p>Discuss incentives for energy-efficient housing projects to meet growing demand while reducing environmental impact.</p>" }
    ],
    meetings: [
      { title: "Community Forum on Rental Assistance Programs",
        description: "<p>Hear from housing authorities about expanding rental aid and share experiences to refine support services.</p>",
        location: "Bell Street Community Center" },
      { title: "Public Hearing on Zoning Reforms for Housing",
        description: "<p>Provide input on updating zoning laws to allow more mixed-use developments and affordable units in key areas.</p>",
        location: "Montgomery City Hall" }
    ]
  },
  "public-safety" => {
    debates: [
      { title: "Enhancing Community Policing Strategies",
        description: "<p>Debate ways to build trust between law enforcement and residents through transparent and collaborative safety initiatives.</p>" },
      { title: "Improving Emergency Response Times",
        description: "<p>Discuss resource allocation to reduce response times for fire and medical emergencies in underserved Montgomery areas.</p>" }
    ],
    meetings: [
      { title: "Town Hall on Neighborhood Watch Programs",
        description: "<p>Join police and community leaders to develop and expand local watch groups for safer neighborhoods.</p>",
        location: "Rosa Parks Library and Museum" },
      { title: "Public Workshop on Crime Prevention Education",
        description: "<p>Learn about educational programs on crime prevention and contribute ideas for youth involvement.</p>",
        location: "Cramton Bowl Multiplex" }
    ]
  },
  "transportation" => {
    debates: [
      { title: "Expanding Public Transit Routes",
        description: "<p>Explore options to extend bus services to connect more Montgomery suburbs with downtown employment centers.</p>" },
      { title: "Promoting Bicycle and Pedestrian Infrastructure",
        description: "<p>Debate investments in bike lanes and sidewalks to encourage safe, eco-friendly commuting alternatives.</p>" }
    ],
    meetings: [
      { title: "Community Session on Traffic Congestion Solutions",
        description: "<p>Discuss traffic management plans with transportation officials and suggest improvements for high-traffic corridors.</p>",
        location: "Montgomery Regional Airport Conference Center" },
      { title: "Public Hearing on Ride-Sharing Initiatives",
        description: "<p>Review proposals for integrating ride-sharing with public transit and gather feedback on accessibility enhancements.</p>",
        location: "Alabama State University - Student Center" }
    ]
  },
  "health" => {
    debates: [
      { title: "Increasing Access to Mental Health Services",
        description: "<p>Discuss community-based approaches to expand mental health resources and reduce stigma in Montgomery.</p>" },
      { title: "Combating Obesity Through Nutrition Programs",
        description: "<p>Explore school and community initiatives to promote healthy eating and physical activity for all age groups.</p>" }
    ],
    meetings: [
      { title: "Town Hall on Vaccination Outreach",
        description: "<p>Engage with health experts on strategies to boost vaccination rates and address public concerns.</p>",
        location: "Montgomery Public Health Department" },
      { title: "Public Workshop on Senior Health Care",
        description: "<p>Share ideas for improving health services tailored to Montgomery's elderly population.</p>",
        location: "Chisholm Community Center" }
    ]
  },
  "education" => {
    debates: [
      { title: "Enhancing STEM Education in Schools",
        description: "<p>Debate funding and curriculum changes to strengthen STEM programs in Montgomery public schools.</p>" },
      { title: "Supporting Adult Education and Workforce Training",
        description: "<p>Discuss expanding adult learning opportunities to bridge skill gaps and boost career advancement.</p>" }
    ],
    meetings: [
      { title: "Community Forum on School Safety Measures",
        description: "<p>Review and provide input on protocols to ensure safe learning environments for students.</p>",
        location: "Montgomery Board of Education Building" },
      { title: "Public Session on After-School Programs",
        description: "<p>Collaborate on developing enriching after-school activities for youth development.</p>",
        location: "Loveless Community Center" }
    ]
  },
  "economy" => {
    debates: [
      { title: "Fostering Small Business Growth",
        description: "<p>Explore incentives and support systems to help local entrepreneurs thrive in Montgomery's economy.</p>" },
      { title: "Attracting Tourism and Investment",
        description: "<p>Debate marketing strategies to highlight Montgomery's history and attract visitors and businesses.</p>" }
    ],
    meetings: [
      { title: "Town Hall on Job Training Initiatives",
        description: "<p>Discuss partnerships for workforce development programs to match skills with local job opportunities.</p>",
        location: "Montgomery Area Chamber of Commerce" },
      { title: "Public Workshop on Economic Development Plans",
        description: "<p>Provide feedback on city plans to stimulate economic growth in key sectors.</p>",
        location: "Dexter Avenue King Memorial Baptist Church Community Center" }
    ]
  },
  "parks-culture" => {
    debates: [
      { title: "Revitalizing Public Parks and Recreation Areas",
        description: "<p>Discuss improvements to make parks more inclusive and family-friendly for Montgomery residents.</p>" },
      { title: "Preserving Cultural Heritage Sites",
        description: "<p>Explore ways to protect and promote Montgomery's historical landmarks for educational and tourism purposes.</p>" }
    ],
    meetings: [
      { title: "Community Session on Arts Funding",
        description: "<p>Engage in talks about allocating resources for local arts programs and cultural events.</p>",
        location: "Montgomery Museum of Fine Arts" },
      { title: "Public Hearing on Park Maintenance Projects",
        description: "<p>Review plans for upgrading park facilities and gather ideas for community involvement.</p>",
        location: "Riverfront Park Amphitheater" }
    ]
  },
  "governance" => {
    debates: [
      { title: "Improving Transparency in City Budgeting",
        description: "<p>Debate methods to make municipal budgeting processes more accessible and participatory for citizens.</p>" },
      { title: "Enhancing Voter Engagement and Education",
        description: "<p>Discuss initiatives to increase voter turnout and inform residents about local elections and policies.</p>" }
    ],
    meetings: [
      { title: "Town Hall on Ethical Governance Practices",
        description: "<p>Join officials to address standards for transparency and accountability in city operations.</p>",
        location: "Montgomery City Hall" },
      { title: "Public Workshop on Community Advisory Boards",
        description: "<p>Explore forming advisory groups to better represent diverse voices in governance decisions.</p>",
        location: "Alabama Department of Archives and History" }
    ]
  }
}

# ── 3. Peupler debates et meetings pour chaque processus ───────────────────
puts "\n[2] Création debates et meetings civiques..."

start_base = Time.zone.now + 7.days

Decidim::ParticipatoryProcess.where.not(id: nil).order(:id).each do |process|
  slug = process.slug
  data = CONTENT[slug]
  next unless data

  puts "\n  Process: #{process.title['en']} (#{slug})"

  # Trouver ou créer composant Debates
  debate_comp = process.components.find_by(manifest_name: 'debates')
  unless debate_comp
    debate_comp = Decidim::Component.create!(
      manifest_name: 'debates',
      name: { en: 'Debates' },
      participatory_space: process,
      published_at: Time.current,
      settings: { comments_enabled: true, comments_max_length: 1000 }
    )
    puts "    ✓ Composant Debates créé"
  end

  # Supprimer anciens debates lorem ipsum sur ce composant
  Decidim::Debates::Debate.where(decidim_component_id: debate_comp.id).destroy_all

  # Créer nouveaux debates
  data[:debates].each do |d|
    Decidim::Debates::Debate.create!(
      title: { en: d[:title] },
      description: { en: d[:description] },
      instructions: { en: "<p>Please keep discussion constructive and solution-oriented.</p>" },
      decidim_component_id: debate_comp.id,
      decidim_author_id: admin.id,
      decidim_author_type: 'Decidim::User',
      start_time: start_base,
      end_time: start_base + 30.days,
    )
    puts "    ✓ Debate: #{d[:title]}"
  end

  # Trouver ou créer composant Meetings
  meeting_comp = process.components.find_by(manifest_name: 'meetings')
  unless meeting_comp
    meeting_comp = Decidim::Component.create!(
      manifest_name: 'meetings',
      name: { en: 'Meetings' },
      participatory_space: process,
      published_at: Time.current,
      settings: {}
    )
    puts "    ✓ Composant Meetings créé"
  end

  # Supprimer anciens meetings lorem ipsum
  Decidim::Meetings::Meeting.where(decidim_component_id: meeting_comp.id).destroy_all

  # Créer nouveaux meetings
  data[:meetings].each_with_index do |m, i|
    meeting_start = start_base + (i * 14).days
    Decidim::Meetings::Meeting.create!(
      title: { en: m[:title] },
      description: { en: m[:description] },
      location: { en: m[:location] },
      location_hints: { en: "Montgomery, Alabama" },
      start_time: meeting_start,
      end_time: meeting_start + 2.hours,
      decidim_component_id: meeting_comp.id,
      registration_type: 'registration_disabled',
      type_of_meeting: 'in_person',
      decidim_author_id: admin.id,
      decidim_author_type: 'Decidim::User',
    )
    puts "    ✓ Meeting: #{m[:title]}"
  end
end

# ── 4. Mettre à jour les static pages ──────────────────────────────────────
puts "\n[3] Mise à jour des static pages..."

pages_content = {
  "terms-of-service" => {
    title: "Terms of Service — Momentum MGM",
    content: "<p>By participating in the Momentum MGM platform, you agree to engage respectfully and constructively. All contributions must be relevant to civic life in Montgomery, Alabama. Harassment, hate speech, or personal attacks will not be tolerated. The City of Montgomery reserves the right to moderate content that violates these terms.</p>"
  },
  "help" => {
    title: "How to Use Momentum MGM",
    content: "<p>Momentum MGM is Montgomery's civic intelligence platform. You can <strong>browse proposals</strong> by category, <strong>vote on ideas</strong> submitted by fellow citizens, <strong>join debates</strong> on key civic issues, and <strong>attend public meetings</strong> to engage directly with city officials. Your voice shapes Montgomery's future.</p>"
  },
  "participatory_processes" => {
    title: "What are Civic Processes?",
    content: "<p>Civic processes are structured spaces where Montgomery residents can participate in decisions that affect their neighborhoods. Each process focuses on one of our 10 civic categories — from infrastructure to governance. Browse proposals, vote, debate, and attend meetings to make your voice heard.</p>"
  },
  "assemblies" => {
    title: "Community Assemblies",
    content: "<p>Community assemblies bring together residents, city officials, and civic organizations to deliberate on key issues facing Montgomery. Assemblies are open to all residents and serve as a bridge between citizen proposals and city policy decisions.</p>"
  },
  "democratic-quality-indicators" => {
    title: "Civic Participation Metrics",
    content: "<p>Momentum MGM tracks civic engagement across Montgomery: number of active proposals, voter participation rates, debate activity, and meeting attendance. These metrics help the city measure the health of participatory democracy and identify areas needing outreach.</p>"
  }
}

Decidim::StaticPage.all.each do |page|
  content = pages_content[page.slug]
  next unless content
  page.update_columns(
    title: { "en" => content[:title] },
    content: { "en" => content[:content] }
  )
  puts "  ✓ Page '#{page.slug}' mise à jour"
end

puts "\n=== Setup terminé ✓ ==="
