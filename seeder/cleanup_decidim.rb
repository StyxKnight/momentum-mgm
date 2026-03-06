puts "=== Momentum MGM — Cleanup & Civic Enrichment ==="

org   = Decidim::Organization.first
admin = Decidim::User.find_by(email: "admin@mgm.styxcore.dev")

# ── 1. Supprimer composants vraiment orphelins des 2 assemblies ──────────────
# Sortitions et Accountability = inutilisés dans une plateforme civique réelle
puts "\n[1] Nettoyage composants orphelins (sortitions + accountability)..."
ORPHAN_COMPONENT_NAMES = %w[sortitions accountability].freeze
Decidim::Assembly.all.each do |assembly|
  assembly.components.where(manifest_name: ORPHAN_COMPONENT_NAMES).each do |comp|
    comp.destroy!
    puts "  ✓ #{assembly.slug} → composant '#{comp.manifest_name}' supprimé"
  end
end

# ── 2. Supprimer meetings lorem ipsum dans les assemblies ─────────────────────
# BUG-012: destroy! trigger callbacks searchable qui crashent sur seed data
# Fix: DELETE SQL direct pour bypasser tous les callbacks Decidim
puts "\n[2] Suppression meetings lorem ipsum dans les assemblies..."
Decidim::Assembly.all.each do |assembly|
  assembly.components.where(manifest_name: 'meetings').each do |comp|
    Decidim::Meetings::Meeting.where(decidim_component_id: comp.id).each do |m|
      title = m.title['en'] rescue m.id.to_s
      ActiveRecord::Base.connection.execute(
        "DELETE FROM decidim_meetings_meetings WHERE id = '#{m.id}'"
      )
      puts "  ✓ Supprimé: #{title}"
    end
  end
end

# ── 3. Supprimer meetings orphelins (aucun component) ────────────────────────
puts "\n[3] Suppression meetings orphelins (component_id nil)..."
Decidim::Meetings::Meeting.all.each do |m|
  next unless m.component.nil?
  title = m.title['en'] rescue m.id.to_s
  ActiveRecord::Base.connection.execute(
    "DELETE FROM decidim_meetings_meetings WHERE id = '#{m.id}'"
  )
  puts "  ✓ Orphelin supprimé: #{title}"
end

# ── 4. Dates sur les 10 processus civiques ───────────────────────────────────
puts "\n[4] Dates 2026 sur les 10 processus..."
Decidim::ParticipatoryProcess.all.each do |p|
  p.update_columns(start_date: Date.new(2026, 1, 1), end_date: Date.new(2026, 12, 31))
  puts "  ✓ #{p.slug}"
end

# ── 5. Renommer les 2 assemblies lorem ipsum ──────────────────────────────────
puts "\n[5] Renommage des assemblies..."

assembly1 = Decidim::Assembly.find_by(id: 1)
if assembly1
  assembly1.update_columns(
    title:       { "en" => "Envision Montgomery 2040 — Citizens Forum" },
    subtitle:    { "en" => "Shape the future of Montgomery together" },
    slug:        "envision-2040",
    short_description: { "en" => "<p>The official citizen engagement space for the Envision Montgomery 2040 Comprehensive Plan — Montgomery's long-term vision for housing, transportation, economic development, parks, and quality of life through 2040.</p>" },
    description: { "en" => "<p>Envision Montgomery 2040 is the City of Montgomery's community-driven Comprehensive Plan, guiding land use, transportation, housing, economic development, parks, and quality of life decisions through 2040. This forum is where residents directly shape that future. Submit ideas, join debates, respond to surveys, and track how community input becomes city policy.</p><p>Key focus areas include the <strong>Downtown Action Plan</strong>, the <strong>Southern Boulevard Corridor</strong>, West Side neighborhood revitalization following the historic $36.6M Neighborhood Access &amp; Equity Grant, and the Centennial Hill Choice Neighborhoods Initiative.</p>" },
    purpose_of_action: { "en" => "<p>To translate the Envision Montgomery 2040 Comprehensive Plan into lived reality by centering resident voices in every major planning decision.</p>" }
  )
  puts "  ✓ Assembly 1 → 'Envision Montgomery 2040 — Citizens Forum'"
end

assembly2 = Decidim::Assembly.find_by(id: 2)
if assembly2
  assembly2.update_columns(
    title:       { "en" => "Montgomery Community Development Fund" },
    subtitle:    { "en" => "You decide how federal funds are spent" },
    slug:        "community-development-fund",
    short_description: { "en" => "<p>Montgomery's participatory budgeting process for federal Community Development Block Grant (CDBG), HOME Investment Partnerships, and Emergency Solutions Grant funds. $2.7M in federal funds — you vote on the projects.</p>" },
    description: { "en" => "<p>Every year, the City of Montgomery receives federal housing and community development funds from HUD: approximately $1.7M in Community Development Block Grants (CDBG), $852,000 in HOME Investment Partnerships, and $146,000 in Emergency Solutions Grants. Federal law requires the city to consult with residents on how these funds are used.</p><p>This is that consultation — but built for real democratic participation. Browse the proposed projects, vote on your priorities, submit your own project ideas, and fill out the survey to tell us what your neighborhood needs most. The results directly inform Montgomery's 2025-2029 HUD Consolidated Plan.</p>" },
    purpose_of_action: { "en" => "<p>To give Montgomery residents direct democratic control over how $2.7M in federal community development funds are allocated — from housing rehabilitation to neighborhood revitalization to emergency homelessness services.</p>" }
  )
  puts "  ✓ Assembly 2 → 'Montgomery Community Development Fund'"
end

# ── 6. Blog — Assembly 1 (Envision 2040) ─────────────────────────────────────
puts "\n[6] Blog posts — Envision 2040 Citizens Forum..."

blog_comp_1 = assembly1&.components&.find_by(manifest_name: 'blogs')
if blog_comp_1
  Decidim::Blogs::Post.where(decidim_component_id: blog_comp_1.id).each do |p|
    p.coauthorships.destroy_all rescue nil
    ActiveRecord::Base.connection.execute("DELETE FROM decidim_blogs_posts WHERE id = #{p.id}")
  end

  [
    {
      title: "Welcome to Momentum MGM — Montgomery's Civic AI Platform",
      body:  "<p>Momentum MGM is Montgomery's first AI-powered civic participation platform, launched during the World Wide Vibes Hackathon (March 5–9, 2026) and built to stay. It connects resident voices directly to city decision-making through a live data lake, AI-assisted analysis, and real participatory democracy tools.</p><p>This platform integrates with the <strong>Envision Montgomery 2040</strong> comprehensive planning process, Montgomery's live Census data (11,000+ data points across 71 census tracts), real estate and business conditions from 500+ data sources, and the City's 311 service request system. When you submit a proposal here, our AI connects it to neighborhood-level data, comparable city solutions, and available federal programs.</p><p>Start by browsing the 10 civic categories, submitting your first proposal, or joining a debate. Your voice is the data.</p>"
    },
    {
      title: "Envision Montgomery 2040: What It Is and Why Your Input Matters Now",
      body:  "<p><strong>Envision Montgomery 2040</strong> is the City of Montgomery's comprehensive plan — the foundational document that guides every major land use, zoning, transportation, housing, and economic development decision through 2040. It was developed through one of the city's most extensive community engagement processes in decades.</p><p>Key priorities from the Envision 2040 plan that this platform directly supports:</p><ul><li><strong>West Side Revitalization</strong> — The city recently secured a historic $36.6M Neighborhood Access &amp; Equity Grant to repair decades of disinvestment caused by I-85 construction and redlining, restoring streets, mobility, and cultural landmarks.</li><li><strong>Centennial Hill</strong> — Montgomery's historic African American downtown neighborhood, bisected by I-85 in the 1960s, is an active Opportunity Zone and USDA-designated food desert. The Choice Neighborhoods Initiative is funding revitalization.</li><li><strong>Downtown Action Plan</strong> — Connecting the Whitewater Rafting Park to the Cypress Preserve via a riverfront trail, activating the Southern Boulevard corridor, and restoring downtown as the heart of the city.</li></ul><p>Every proposal you submit through Momentum MGM's 10 civic processes feeds directly into this planning framework. The data is real. The decisions are real.</p>"
    }
  ].each do |post_data|
    Decidim::Blogs::Post.new(
      title:               { en: post_data[:title] },
      body:                { en: post_data[:body] },
      decidim_component_id: blog_comp_1.id,
      decidim_author_id:   admin.id,
      decidim_author_type: admin.class.name,
      published_at:        Time.current
    ).save!(validate: false)
    puts "  ✓ #{post_data[:title][0..70]}"
  end
end

# ── 7. Blog — Assembly 2 (Community Development Fund) ────────────────────────
puts "\n[7] Blog posts — Community Development Fund..."

blog_comp_2 = assembly2&.components&.find_by(manifest_name: 'blogs')
if blog_comp_2
  Decidim::Blogs::Post.where(decidim_component_id: blog_comp_2.id).each do |p|
    p.coauthorships.destroy_all rescue nil
    ActiveRecord::Base.connection.execute("DELETE FROM decidim_blogs_posts WHERE id = #{p.id}")
  end

  [
    {
      title: "How Montgomery's Federal Community Development Funds Work — And How You Decide",
      body:  "<p>Each year, the City of Montgomery receives three federal grants from the U.S. Department of Housing and Urban Development (HUD) to invest in low- and moderate-income neighborhoods:</p><ul><li><strong>Community Development Block Grant (CDBG): ~$1.7M</strong> — for housing, economic development, community facilities, infrastructure, and public services in low-income areas.</li><li><strong>HOME Investment Partnerships: ~$852,000</strong> — exclusively for affordable housing: rehabilitation, new construction, and rental assistance for households below 80% Area Median Income.</li><li><strong>Emergency Solutions Grant (ESG): ~$146,000</strong> — for emergency shelter, rapid rehousing, and homelessness prevention services.</li></ul><p>Federal law (the HUD Consolidated Plan regulation) requires cities to consult with residents before deciding how these funds are used. Montgomery submitted its 2025-2029 Consolidated Plan to HUD in mid-2025. This platform is how that consultation becomes real democratic participation — not just a survey buried on a government website. Vote on the proposed projects below. The results are shared with the Community Development Division.</p>"
    },
    {
      title: "$36.6M West Side Grant: Montgomery Makes History — Help Shape the Plan",
      body:  "<p>In a historic win for environmental and racial equity, Montgomery secured a <strong>$36.6 million Neighborhood Access and Equity Grant</strong> — one of the largest federal equity investments in the city's history. The grant directly addresses the legacy of redlining and the construction of Interstate 85, which bisected and destroyed West Side neighborhoods in the 1960s and 1970s, separating communities from downtown, jobs, and services.</p><p>Funded priorities include:</p><ul><li>Creating safer streets and improved mobility in the communities cut off by I-85</li><li>Preserving and celebrating West Side cultural landmarks</li><li>Restoring pedestrian and bicycle connections between West Side neighborhoods and the city center</li><li>Supporting community-led economic revitalization</li></ul><p>Implementation planning is underway. The Community Development Division is collecting resident input on project priorities. Use the survey in this space and the proposals in the <strong>Infrastructure</strong> and <strong>Transportation</strong> civic processes to tell us what matters most to your community.</p>"
    }
  ].each do |post_data|
    Decidim::Blogs::Post.new(
      title: { en: post_data[:title] },
      body:  { en: post_data[:body] },
      decidim_component_id: blog_comp_2.id,
      decidim_author_id:   admin.id,
      decidim_author_type: admin.class.name,
      published_at:        Time.current
    ).save!(validate: false)
    puts "  ✓ #{post_data[:title][0..70]}"
  end
end

# ── 8. Budget participatif — Assembly 2 ──────────────────────────────────────
puts "\n[8] Budget participatif CDBG/HOME/ESG — Community Development Fund..."

budget_comp = assembly2&.components&.find_by(manifest_name: 'budgets')
if budget_comp
  Decidim::Budgets::Budget.where(decidim_component_id: budget_comp.id).each do |b|
    b.projects.destroy_all
    b.destroy!
  end

  budget = Decidim::Budgets::Budget.create!(
    title:       { en: "Montgomery Federal Community Development Allocation 2026" },
    description: { en: "<p>Below are the proposed uses for Montgomery's $2,698,000 in federal HUD funds for 2026 (CDBG + HOME + ESG). Vote on the projects that matter most to your neighborhood. Results inform the 2025-2029 HUD Consolidated Plan allocation decisions.</p>" },
    total_budget: 2_698_000,
    decidim_component_id: budget_comp.id,
    weight: 0
  )

  [
    {
      title: "Affordable Housing Rehabilitation — Low-Income Homeowners (HOME)",
      description: "<p>Rehabilitation of 40+ owner-occupied homes for low-income households across Montgomery. Priority neighborhoods: West Montgomery, Centennial Hill, and areas along the Carter Hill Road corridor. Repairs include roofing, HVAC, electrical, and ADA accessibility modifications. Funded by HOME Investment Partnerships funds ($852K). Households must earn below 80% Area Median Income ($52,400/yr for a family of 4).</p>",
      amount: 852_000
    },
    {
      title: "West Side Streets & Mobility — $36.6M Grant Local Match Support",
      description: "<p>Local co-investment to support implementation of the $36.6M Neighborhood Access and Equity Grant on Montgomery's West Side. Funds community engagement, design, and local match requirements for pedestrian infrastructure, safer crossings, and mobility improvements in neighborhoods historically cut off by I-85 construction. West Side communities have been separated from downtown employment and services since the 1960s.</p>",
      amount: 400_000
    },
    {
      title: "Centennial Hill Food Access & Neighborhood Services",
      description: "<p>Centennial Hill — Montgomery's historic African American downtown neighborhood, bisected by I-85 — is designated a food desert by the USDA and an Opportunity Zone by the U.S. Treasury. This project funds a mobile food pantry partnership, community health worker outreach, and support services for the 2,000+ residents of the Centennial Hill public housing community currently undergoing Choice Neighborhoods revitalization.</p>",
      amount: 300_000
    },
    {
      title: "East Fairview & Carter Hill Road Streetscape Implementation",
      description: "<p>Implementation funding for two ARPA-funded streetscape master plans currently in final design: the East Fairview Streetscape Master Plan and the Carter Hill Road &amp; College Street Streetscape Master Plan. Projects include new sidewalks, street lighting, ADA-compliant curb cuts, and traffic calming in historically underinvested corridors. CDBG funds the community engagement and accessibility components.</p>",
      amount: 354_000
    },
    {
      title: "Emergency Housing Stability — ESG Rapid Rehousing",
      description: "<p>Emergency Solutions Grant (ESG) funding for two programs: (1) emergency shelter operations for families with nowhere to go, and (2) rapid rehousing — short-term rental assistance plus case management to move homeless individuals and families into stable housing within 30 days. Montgomery's citywide homelessness initiative prioritizes chronically homeless veterans, families with children, and survivors of domestic violence.</p>",
      amount: 146_000
    },
    {
      title: "Urban League Youth Workforce Pipeline — Districts 4, 6, 8",
      description: "<p>In partnership with the Urban League of Alabama's new Montgomery expansion, this project funds job training, credentialing, and employer placement services for 150+ young adults (18–24) in historically high-poverty districts. Priority sectors: advanced manufacturing (Hyundai supply chain), healthcare, and construction trades. The Urban League partnership was announced by Mayor Reed and covers workforce development, small business support, and community empowerment.</p>",
      amount: 346_000
    },
    {
      title: "SEED Academy — Emerging Real Estate Developers Program",
      description: "<p>Support for Mayor Reed's SEED Academy, which cultivates a new generation of Montgomery real estate developers from underrepresented communities. CDBG funds cover participant stipends, technical assistance, and predevelopment costs for pilot projects in Centennial Hill and the West End. The Academy addresses the long-term structural gap: Montgomery's development capacity is concentrated in a small number of firms, leaving low-income neighborhoods chronically underserved.</p>",
      amount: 300_000
    }
  ].each do |proj|
    Decidim::Budgets::Project.create!(
      title:       { en: proj[:title] },
      description: { en: proj[:description] },
      budget_amount: proj[:amount],
      budget: budget,
    )
    formatted = proj[:amount].to_s.reverse.scan(/\d{1,3}/).join(',').reverse
    puts "  ✓ $#{formatted} — #{proj[:title][0..65]}"
  end
end

# ── 9. Surveys ────────────────────────────────────────────────────────────────
# Assembly 1: Envision 2040 priorities
# Assembly 2: CDBG allocation priorities
# 10 processes: civic questionnaires per category

def create_survey(component, title, description, questions)
  # Clear existing
  Decidim::Surveys::Survey.where(decidim_component_id: component.id).each do |s|
    if s.questionnaire
      s.questionnaire.questions.each { |q| q.response_options.destroy_all rescue nil; q.destroy! }
      s.questionnaire.destroy!
    end
    s.destroy!
  end

  survey = Decidim::Surveys::Survey.new(decidim_component_id: component.id).tap { |s| s.save!(validate: false) }
  questionnaire = Decidim::Forms::Questionnaire.create!(
    title:       { en: title },
    description: { en: description },
    tos:         { en: "<p>All responses are anonymous and used solely to improve city services and inform civic planning decisions.</p>" },
    questionnaire_for: survey
  )
  questions.each_with_index do |q_data, idx|
    question = Decidim::Forms::Question.create!(
      questionnaire: questionnaire,
      body: { en: q_data[:body] },
      question_type: q_data[:type],
      position: idx,
      mandatory: false
    )
    q_data[:options]&.each do |opt|
      Decidim::Forms::ResponseOption.create!(
        question: question,
        body: { en: opt },
        free_text: false
      )
    end
    puts "    Q#{idx + 1}: #{q_data[:body][0..65]}"
  end
  survey
end

puts "\n[9] Surveys..."

# Survey — Assembly 1: Envision 2040
survey_comp_1 = assembly1&.components&.find_by(manifest_name: 'surveys')
if survey_comp_1
  puts "  Assembly: Envision Montgomery 2040 Citizens Forum"
  create_survey(
    survey_comp_1,
    "Envision Montgomery 2040 — Resident Priorities Survey",
    "<p>Help shape Montgomery's Comprehensive Plan through 2040. This survey collects resident priorities across housing, transportation, economic development, parks, and quality of life. Results are shared with the Montgomery Planning Commission.</p>",
    [
      { body: "What is the single most important issue facing Montgomery that the 2040 Comprehensive Plan must address?",
        type: "single_option",
        options: ["Affordable housing shortage", "Poverty and economic inequality", "Crime and public safety", "Crumbling infrastructure and roads", "Lack of public transportation", "Environmental issues (flooding, heat, air quality)", "Population decline and blight", "Lack of jobs and economic opportunity"] },
      { body: "Which Montgomery neighborhood or area do you live in or represent?",
        type: "single_option",
        options: ["Downtown / Midtown", "West Side / West End", "Centennial Hill", "East Montgomery", "South Montgomery", "North Montgomery / Chisholm", "Old Cloverdale / Garden District", "Other / citywide"] },
      { body: "The City secured a $36.6M grant to repair damage caused by I-85 to West Side neighborhoods. What should be the top priority for these funds?",
        type: "single_option",
        options: ["Pedestrian safety and crossings", "Bicycle infrastructure and trails", "Business corridor revitalization", "Cultural landmark preservation", "Green spaces and parks", "Affordable housing development", "Community center or gathering spaces"] },
      { body: "Montgomery's FY2026 budget cuts Parks & Recreation by ~$6M while increasing road maintenance. Do you agree with this trade-off?",
        type: "single_option",
        options: ["Yes — roads are the bigger priority", "No — parks and youth programs are essential", "Only if park cuts are temporary", "Neither — both should be fully funded", "I don't have enough information to say"] },
      { body: "What additional comments do you have for the Envision Montgomery 2040 planning team?",
        type: "long_response" }
    ]
  )
end

# Survey — Assembly 2: CDBG
survey_comp_2 = assembly2&.components&.find_by(manifest_name: 'surveys')
if survey_comp_2
  puts "  Assembly: Community Development Fund"
  create_survey(
    survey_comp_2,
    "How Should Montgomery Allocate Its $2.7M in Federal Community Development Funds?",
    "<p>Montgomery receives approximately $2.7M annually in federal HUD funds: Community Development Block Grant (CDBG), HOME Investment Partnerships, and Emergency Solutions Grant. Federal regulations require the city to consult with residents. This survey directly informs the 2025-2029 HUD Consolidated Plan priority allocations.</p>",
    [
      { body: "Which community need should receive the largest share of CDBG funds?",
        type: "single_option",
        options: ["Affordable housing rehabilitation for homeowners", "Neighborhood infrastructure (sidewalks, lighting, streetscapes)", "Economic development and small business support", "Youth workforce training and job placement", "Community health and food access programs", "Homeless prevention and emergency shelter"] },
      { body: "Are you aware that Montgomery receives ~$1.7M in CDBG federal funds each year and that residents have the right to shape how it's spent?",
        type: "single_option",
        options: ["Yes, I knew this", "No, I had no idea", "I knew federal funds exist but not the amounts", "I knew and have participated in the process before"] },
      { body: "Which Montgomery neighborhood do you think most needs investment from these federal community development funds?",
        type: "single_option",
        options: ["Centennial Hill", "West Side / West End", "South Hull / Cleveland Avenue corridor", "North Montgomery / Chisholm", "East Montgomery", "Downtown / Midtown", "Multiple neighborhoods equally", "I don't know enough to say"] },
      { body: "What type of housing program is most needed in your community?",
        type: "multiple_option",
        options: ["Home repair for low-income owners", "New affordable rental units", "Down payment assistance for first-time buyers", "Emergency rental assistance to prevent eviction", "Senior and accessible housing", "Transitional housing for people leaving homelessness"] },
      { body: "What additional input do you have for Montgomery's Community Development Division on how these funds should be used?",
        type: "long_response" }
    ]
  )
end

# Surveys — 10 Participatory Processes
PROCESS_SURVEYS = {
  "infrastructure" => {
    title: "Infrastructure & Roads — What Needs Fixing Most in Your Neighborhood?",
    desc:  "<p>Montgomery's FY2026 budget adds $2.2M for road maintenance and significantly increases the traffic engineering budget. Three ARPA-funded streetscape master plans are also in design (East Fairview, Carter Hill Road, Greater Floyd Campus). Help prioritize where these investments go.</p>",
    questions: [
      { body: "How would you rate road and infrastructure conditions in your immediate neighborhood?",
        type: "single_option",
        options: ["Very Good", "Good", "Fair — needs attention", "Poor", "Very Poor — dangerous"] },
      { body: "Which infrastructure problem affects your daily life most?",
        type: "single_option",
        options: ["Potholes and cracked pavement", "Flooding and stormwater drainage", "Missing or broken sidewalks", "Poor street lighting", "Bridge or overpass conditions", "Water main breaks or reliability issues"] },
      { body: "What neighborhood or street needs the most urgent attention?",
        type: "short_response" },
      { body: "Additional comments for the Public Works Department:",
        type: "long_response" }
    ]
  },
  "environment" => {
    title: "Environment & Sustainability — What Environmental Issues Affect You Most?",
    desc:  "<p>Montgomery faces significant environmental challenges including urban heat islands, Alabama River water quality, flooding, and food deserts (Centennial Hill is USDA-designated). Share your experience and priorities.</p>",
    questions: [
      { body: "Which environmental issue most directly affects your quality of life in Montgomery?",
        type: "single_option",
        options: ["Urban flooding and poor drainage", "Extreme heat with no shade or green space", "Air quality near industrial areas", "No access to fresh food (food desert)", "Alabama River water quality", "Lack of recycling or waste services", "Abandoned lots and urban blight"] },
      { body: "Do you live in or near a neighborhood designated as a food desert?",
        type: "single_option",
        options: ["Yes — Centennial Hill area", "Yes — West Side / West End", "Yes — other neighborhood", "No", "Not sure"] },
      { body: "Would you participate in community environmental programs (tree planting, cleanups, community gardens)?",
        type: "single_option",
        options: ["Yes, definitely", "Probably", "Not sure", "Probably not", "No"] },
      { body: "What environmental improvement would most benefit your neighborhood?",
        type: "long_response" }
    ]
  },
  "housing" => {
    title: "Housing & Neighborhoods — Your Housing Reality in Montgomery",
    desc:  "<p>21.2% of Montgomery residents live below the poverty line. The city's West Side received a $36.6M federal equity grant. Centennial Hill is undergoing Choice Neighborhoods revitalization. The SEED Academy is cultivating new affordable housing developers. Tell us your housing situation and needs.</p>",
    questions: [
      { body: "What is your current housing situation?",
        type: "single_option",
        options: ["Own my home — paid off", "Own my home — with mortgage", "Renting an apartment or house", "Staying with family/friends due to cost", "In transitional or temporary housing", "Other"] },
      { body: "Have you spent more than 30% of your household income on housing costs in the past year?",
        type: "single_option",
        options: ["Yes, consistently", "Yes, sometimes", "No", "Not sure"] },
      { body: "Which housing program would most benefit your household?",
        type: "multiple_option",
        options: ["Home repair or rehabilitation grant", "Down payment assistance", "Emergency rental assistance", "Affordable housing waitlist", "Eviction prevention counseling", "Senior / accessible housing", "New affordable rental units in my neighborhood"] },
      { body: "What is your neighborhood and what is the biggest housing challenge there?",
        type: "long_response" }
    ]
  },
  "public-safety" => {
    title: "Public Safety — Your Experience and Priorities",
    desc:  "<p>Mayor Reed reported a major drop in overall crime in early 2026, supported by a new police communication system and expanded security cameras funded in the FY2026 budget. Violent crime remains a concern in specific areas. Your input helps allocate public safety resources equitably.</p>",
    questions: [
      { body: "How safe do you feel in your neighborhood on a typical evening?",
        type: "single_option",
        options: ["Very Safe", "Safe", "Somewhat unsafe", "Unsafe", "Very Unsafe"] },
      { body: "How would you describe your level of trust in the Montgomery Police Department?",
        type: "single_option",
        options: ["High trust", "Moderate trust", "Low trust", "Very low trust", "No opinion"] },
      { body: "What public safety approach do you most support for Montgomery?",
        type: "multiple_option",
        options: ["More neighborhood police patrols", "Community policing and relationship-building", "Mental health crisis response teams (non-police)", "Youth intervention and diversion programs", "Better street lighting and environmental design", "Expanded neighborhood watch programs", "Security cameras in commercial corridors"] },
      { body: "What would most improve your sense of safety in your neighborhood?",
        type: "long_response" }
    ]
  },
  "transportation" => {
    title: "Transportation — How Do You Get Around Montgomery?",
    desc:  "<p>Montgomery residents consistently report dissatisfaction with public transit access. The $36.6M West Side grant includes mobility improvements for neighborhoods cut off by I-85. Envision 2040 prioritizes a riverfront trail network and better connectivity. Tell us how you travel and what's missing.</p>",
    questions: [
      { body: "What is your primary way of getting around Montgomery for daily trips?",
        type: "single_option",
        options: ["Personal vehicle", "MAX Bus (Montgomery Area Transit)", "Rideshare (Uber/Lyft)", "Walking", "Bicycle", "Combination"] },
      { body: "How satisfied are you with MAX Bus service in your area?",
        type: "single_option",
        options: ["Very Satisfied", "Satisfied", "Neutral", "Dissatisfied — infrequent service", "Dissatisfied — no route near me", "I don't use MAX"] },
      { body: "What is the biggest transportation barrier you face in Montgomery?",
        type: "single_option",
        options: ["No bus route near my home or destination", "Service too infrequent to be useful", "Unsafe walking conditions to bus stops", "Can't afford a car but transit doesn't reach work", "I have a disability and the system is inaccessible", "Nothing — I have a car and it works fine"] },
      { body: "What transportation improvement would change your daily life the most?",
        type: "long_response" }
    ]
  },
  "health" => {
    title: "Health & Wellbeing — Access, Barriers, and Priorities",
    desc:  "<p>Montgomery faces serious public health challenges: ~40% of residents are classified as obese, ~14% experience food insecurity, and mental health is the top community concern in the 2025 Partners in Health community assessment. Access to healthcare, grocery stores, and safe drinking water are all areas of resident dissatisfaction.</p>",
    questions: [
      { body: "How would you rate your ability to access healthcare when you need it?",
        type: "single_option",
        options: ["Excellent — I can always access care", "Good", "Fair — there are gaps", "Poor — significant barriers", "Very Poor — I routinely go without care"] },
      { body: "Which health services are hardest to access in your community?",
        type: "multiple_option",
        options: ["Mental health counseling", "Substance use treatment", "Primary care / family medicine", "Dental care", "Maternal and child health", "Senior care", "Specialty care (cardiology, oncology, etc.)"] },
      { body: "Do you have reliable access to fresh, affordable food near your home?",
        type: "single_option",
        options: ["Yes — grocery store within 1 mile", "Yes — but I need a car to get there", "No — nearest grocery is far and I don't drive", "No — I rely on food banks or corner stores", "Not consistently"] },
      { body: "What health program or service would most help your household?",
        type: "long_response" }
    ]
  },
  "education" => {
    title: "Education & Youth — Schools, Skills, and Opportunity",
    desc:  "<p>Montgomery Public Schools serve over 30,000 students. The Urban League of Alabama recently expanded into Montgomery, adding workforce development, education, and youth empowerment programs. The city's summer programs served 300+ children in civic engagement workshops. Share your experience and priorities.</p>",
    questions: [
      { body: "Do you have children currently enrolled in Montgomery Public Schools?",
        type: "single_option",
        options: ["Yes", "No, but have in the past", "No children in MPS", "Prefer not to say"] },
      { body: "What educational improvement matters most to you?",
        type: "single_option",
        options: ["Modern school facilities and technology", "Stronger STEM programs", "Arts, music, and cultural programs", "More school counselors and mental health support", "Better after-school and summer programs", "Higher teacher pay and retention", "Adult education and GED programs"] },
      { body: "Are workforce training or reskilling programs valuable to your household?",
        type: "single_option",
        options: ["Yes — I'm actively looking for training", "Yes — someone in my household needs it", "Maybe — depends on what's offered", "No — not needed right now", "Already participating in a program"] },
      { body: "What would make the biggest difference for children and young people in Montgomery?",
        type: "long_response" }
    ]
  },
  "economy" => {
    title: "Economy & Employment — Jobs, Opportunity, and Small Business in Montgomery",
    desc:  "<p>Montgomery's FY2026 budget makes a record $8M investment in sports and entertainment facilities as an economic driver. The SEED Academy is growing local real estate development. The Urban League partnership targets workforce development. Tourism hit 1.8M visitors in 2025. What does economic opportunity look like in your daily life?</p>",
    questions: [
      { body: "What best describes your current employment situation?",
        type: "single_option",
        options: ["Employed full-time", "Employed part-time", "Self-employed / business owner", "Unemployed, actively looking", "Not in labor force (retired, disability, caregiver)", "Student"] },
      { body: "What is the biggest economic barrier facing Montgomery residents?",
        type: "single_option",
        options: ["Wages too low relative to cost of living", "Not enough jobs in growing industries", "Skills mismatch — training doesn't match available jobs", "No childcare for working parents", "Transportation barriers to reach employment", "Small businesses can't afford to stay open"] },
      { body: "What type of economic investment would most improve your life or neighborhood?",
        type: "multiple_option",
        options: ["More jobs in my neighborhood", "Microloan or grant for my small business", "Job training in a new career field", "Affordable childcare so I can work more", "Better public transit to reach job centers", "Investment in a specific commercial corridor near me"] },
      { body: "What would most strengthen economic opportunity for families in your neighborhood?",
        type: "long_response" }
    ]
  },
  "parks-culture" => {
    title: "Parks, Culture & Recreation — What Do You Need and What's Being Cut?",
    desc:  "<p>Mayor Reed's FY2026 budget cuts Parks &amp; Recreation by nearly $6M — a controversial decision in a city where summer programs served 300+ children. The Envision 2040 plan calls for a riverfront trail connecting the Whitewater Rafting Park to Cypress Preserve. The $36.6M West Side grant includes cultural landmark preservation. Tell us what parks and culture mean to your community.</p>",
    questions: [
      { body: "How often do you use Montgomery's parks, recreation centers, or cultural facilities?",
        type: "single_option",
        options: ["Almost daily", "Several times a week", "Once a week", "A few times a month", "Rarely", "Never — not accessible to me"] },
      { body: "The FY2026 budget cuts Parks & Recreation by ~$6M. What do you think the city should do?",
        type: "single_option",
        options: ["Restore the parks budget — these services are essential", "Accept the cut — roads and safety are more urgent", "Restore only youth programs and summer camps", "Find alternative funding (grants, partnerships)", "I need more information before deciding"] },
      { body: "What park or cultural improvement would most benefit your family?",
        type: "multiple_option",
        options: ["Better playground equipment", "Splash pads and pools in underserved areas", "Walking and biking trails (riverfront, Cypress Preserve)", "Sports courts (basketball, tennis, pickleball)", "Community gardens", "Cultural events and performance spaces", "Better lighting and safety in existing parks"] },
      { body: "What cultural or recreational program should the city prioritize — and why?",
        type: "long_response" }
    ]
  },
  "governance" => {
    title: "Governance & Democracy — How Well Is Montgomery Listening?",
    desc:  "<p>Montgomery completed its 2025-2029 HUD Consolidated Plan through public meetings and surveys. Envision 2040 was developed through extensive community engagement. Momentum MGM itself is a new civic technology tool built to make that engagement real and continuous. How well is the city doing?</p>",
    questions: [
      { body: "How satisfied are you with how the City of Montgomery communicates with residents?",
        type: "single_option",
        options: ["Very Satisfied", "Satisfied", "Neutral", "Dissatisfied", "Very Dissatisfied"] },
      { body: "Have you ever participated in a public hearing, planning meeting, or city survey?",
        type: "single_option",
        options: ["Yes — in person at a city meeting", "Yes — online/digital survey", "Both in person and online", "No — I wanted to but couldn't find how", "No — I didn't know those existed", "No — I don't feel my input would matter"] },
      { body: "What would make civic participation easier and more meaningful for you?",
        type: "multiple_option",
        options: ["Meetings at evening or weekend hours", "Online and mobile-friendly participation tools", "Better notification — I never hear about meetings", "Childcare at public meetings", "Translation services (Spanish, other languages)", "Clearer follow-up on how input was actually used"] },
      { body: "What one change would most improve how the City of Montgomery engages with residents like you?",
        type: "long_response" }
    ]
  }
}.freeze

puts "\n  Process surveys..."
Decidim::ParticipatoryProcess.all.each do |process|
  data = PROCESS_SURVEYS[process.slug]
  next unless data

  survey_comp = process.components.find_by(manifest_name: 'surveys')
  unless survey_comp
    survey_comp = Decidim::Component.create!(
      manifest_name: 'surveys',
      name: { en: 'Community Survey' },
      participatory_space: process,
      published_at: Time.current,
      settings: { allow_answers: true, allow_unregistered: false }
    )
  end

  puts "\n  Process: #{process.title['en']}"
  create_survey(survey_comp, data[:title], data[:desc], data[:questions])
end

# ── 10. Vérification finale ───────────────────────────────────────────────────
puts "\n=== VÉRIFICATION FINALE ==="
puts "Assemblies:       #{Decidim::Assembly.count}"
puts "Processes:        #{Decidim::ParticipatoryProcess.count}"
puts "Meetings:         #{Decidim::Meetings::Meeting.count}"
puts "Debates:          #{Decidim::Debates::Debate.count}"
puts "Proposals:        #{Decidim::Proposals::Proposal.count}"
puts "Blog posts:       #{Decidim::Blogs::Post.count}"
puts "Budgets:          #{Decidim::Budgets::Budget.count}"
puts "Budget projects:  #{Decidim::Budgets::Project.count}"
puts "Surveys:          #{Decidim::Surveys::Survey.count}"
puts "Survey questions: #{Decidim::Forms::Question.count}"
puts "Components:       #{Decidim::Component.count}"
puts "\n=== Cleanup & enrichment terminé ✓ ==="
