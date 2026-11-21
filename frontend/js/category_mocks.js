/**
 * GapScope Category-Specific Intelligence Mocks
 * Provides realistic, authentic multi-source datasets for categories and competitor deep dives.
 */

export const TRAVEL_REPORT = {
  scan_id: "disc_travel_india",
  mode: 3,
  query: "Travel",
  generated_at: new Date().toISOString(),
  keywords: {
    broad: "travel booking",
    specific: ["flight booking app India", "train ticket booking app", "hotel booking coupons"],
    category: "Travel & Hospitality"
  },
  credits: {
    serpapi_live: 5,
    serpapi_cached: 3,
    youcom_live: 2,
    youcom_cached: 1
  },
  verdict: {
    kind: "discovery",
    label: null,
    score: null,
    headline: "Identified 3 systemic cross-competitor gaps across 5 leading travel booking apps",
    breakdown: [
      {
        factor: "Cross-App Systemic Gaps",
        score: 30,
        max: 30,
        explanation: "3 major grievance clusters span MakeMyTrip, EaseMyTrip, IRCTC, and Yatra",
        evidence_ids: ["ev_tr01", "ev_tr02", "ev_tr03"]
      },
      {
        factor: "Incumbent Saturation",
        score: 20,
        max: 20,
        explanation: "Evaluated top 5 travel apps in India with over 200M combined downloads",
        evidence_ids: []
      }
    ]
  },
  trend: {
    keyword: "travel booking",
    geo: "IN",
    points: [
      { date: "2025-12", value: 65 },
      { date: "2026-01", value: 72 },
      { date: "2026-02", value: 68 },
      { date: "2026-03", value: 74 },
      { date: "2026-04", value: 80 },
      { date: "2026-05", value: 86 },
      { date: "2026-06", value: 88 },
      { date: "2026-07", value: 82 },
      { date: "2026-08", value: 85 },
      { date: "2026-09", value: 91 },
      { date: "2026-10", value: 95 },
      { date: "2026-11", value: 98 }
    ],
    change_pct: 21.6,
    direction: "rising"
  },
  competitors: [
    {
      name: "MakeMyTrip: Flight, Hotel, Bus",
      product_id: "com.makemytrip",
      rating: 4.4,
      installs: "50M+",
      icon: "https://play-lh.googleusercontent.com/1-hPxOdpBED1",
      url: "https://play.google.com/store/apps/details?id=com.makemytrip",
      source: "play_store",
      reviews_scanned: 100
    },
    {
      name: "IRCTC Rail Connect",
      product_id: "cris.org.in.prs.ima",
      rating: 3.7,
      installs: "100M+",
      icon: "https://play-lh.googleusercontent.com/irctc-app",
      url: "https://play.google.com/store/apps/details?id=cris.org.in.prs.ima",
      source: "play_store",
      reviews_scanned: 100
    },
    {
      name: "EaseMyTrip: Flights, Hotels, Bus",
      product_id: "com.easemytrip.android",
      rating: 4.5,
      installs: "10M+",
      icon: "https://play-lh.googleusercontent.com/easemytrip-app",
      url: "https://play.google.com/store/apps/details?id=com.easemytrip.android",
      source: "play_store",
      reviews_scanned: 100
    },
    {
      name: "ConfirmTkt: Train Ticket Booking",
      product_id: "com.confirmtkt.lite",
      rating: 4.6,
      installs: "50M+",
      icon: "https://play-lh.googleusercontent.com/confirmtkt-app",
      url: "https://play.google.com/store/apps/details?id=com.confirmtkt.lite",
      source: "play_store",
      reviews_scanned: 100
    },
    {
      name: "Yatra: Flight, Hotel, Train",
      product_id: "com.yatra.base",
      rating: 4.1,
      installs: "10M+",
      icon: "https://play-lh.googleusercontent.com/yatra-app",
      url: "https://play.google.com/store/apps/details?id=com.yatra.base",
      source: "play_store",
      reviews_scanned: 100
    }
  ],
  clusters: [
    {
      id: "cl_1",
      group: "pain",
      title: "Deceptive Convenience Fees Added at Final Payment Screen",
      summary: "Users report advertised cheap fares balloon by ₹450-₹800 per passenger in mandatory convenience and insurance add-ons on the final UPI step.",
      severity: "high",
      frequency: {
        count: 58,
        total: 500,
        label: "58 of 500 reviews"
      },
      apps_affected: [
        "MakeMyTrip: Flight, Hotel, Bus",
        "EaseMyTrip: Flights, Hotels, Bus",
        "Yatra: Flight, Hotel, Train"
      ],
      evidence_ids: ["ev_tr01", "ev_tr02", "ev_tr04"],
      ai_suggested: false
    },
    {
      id: "cl_2",
      group: "pain",
      title: "Tatkal Payment Deductions Without Ticket Generation",
      summary: "During morning Tatkal slots, bank accounts are debited via UPI but the train booking portal times out, leaving passengers ticketless and waiting 7 days for refunds.",
      severity: "high",
      frequency: {
        count: 47,
        total: 500,
        label: "47 of 500 reviews"
      },
      apps_affected: [
        "IRCTC Rail Connect",
        "ConfirmTkt: Train Ticket Booking"
      ],
      evidence_ids: ["ev_tr03", "ev_tr05"],
      ai_suggested: false
    },
    {
      id: "cl_3",
      group: "pain",
      title: "Delayed Flight Cancellation Refunds Trapped in In-App Wallets",
      summary: "When airlines cancel or reschedule flights, travel aggregators force refunds into non-withdrawable app cash balances rather than returning to source banks.",
      severity: "medium",
      frequency: {
        count: 32,
        total: 500,
        label: "32 of 500 reviews"
      },
      apps_affected: [
        "MakeMyTrip: Flight, Hotel, Bus",
        "Yatra: Flight, Hotel, Train"
      ],
      evidence_ids: ["ev_tr06"],
      ai_suggested: false
    }
  ],
  opportunities: [
    {
      id: "op_1",
      title: "Zero-Convenience-Fee Transparent Flight Booking",
      pitch: "An upfront price commitment where the fare shown on search is the exact penny charged on UPI, eliminating checkout price shock.",
      target_user: "Budget travelers, frequent domestic flyers, and price-conscious youth in India",
      addresses_cluster_ids: ["cl_1"],
      evidence_ids: ["ev_tr01", "ev_tr02"],
      ai_suggested: false
    },
    {
      id: "op_2",
      title: "Zero-Risk Tatkal Queue with Instant Bank Reversal",
      pitch: "High-speed tatkal automated execution that holds payment in an instant escrow and reverses to UPI within 60 seconds if unconfirmed.",
      target_user: "Daily rail commuters and festival season train travelers across Tier 2/3 cities",
      addresses_cluster_ids: ["cl_2"],
      evidence_ids: ["ev_tr03", "ev_tr05"],
      ai_suggested: false
    },
    {
      id: "op_3",
      title: "Direct-to-Bank Airline Refund Autopilot",
      pitch: "Automatic flight cancellation tracking that settles airline refunds directly into user bank accounts without aggregator deductions.",
      target_user: "Corporate business travelers and holiday planners facing airline schedule disruptions",
      addresses_cluster_ids: ["cl_3"],
      evidence_ids: ["ev_tr06"],
      ai_suggested: false
    }
  ],
  news: [],
  evidence: {
    ev_tr01: {
      id: "ev_tr01",
      source: "play_store",
      text: "Showed flight ticket for ₹3800 on search. When I went to UPI payment page, price jumped to ₹4550 with convenience fee, seat fee and auto-checked insurance. Total daylight robbery.",
      title: null,
      author: "Rahul Nair",
      rating: 1,
      date: "2026-10-18",
      url: "https://play.google.com/store/apps/details?id=com.makemytrip",
      entity: "MakeMyTrip: Flight, Hotel, Bus",
      likes: 54
    },
    ev_tr02: {
      id: "ev_tr02",
      source: "play_store",
      text: "They claim zero convenience fees in banners, but they add 'platform facilitation charge' at checkout. Misleading pricing for budget travelers.",
      title: null,
      author: "Aditi Sen",
      rating: 1,
      date: "2026-10-12",
      url: "https://play.google.com/store/apps/details?id=com.easemytrip.android",
      entity: "EaseMyTrip: Flights, Hotels, Bus",
      likes: 38
    },
    ev_tr03: {
      id: "ev_tr03",
      source: "play_store",
      text: "Booked Tatkal at 10 AM. ₹2100 deducted from GPay, but app crashed and showed 'Booking Session Timed Out'. Ticket not booked and money took 5 working days to return.",
      title: null,
      author: "Girish K.",
      rating: 1,
      date: "2026-10-24",
      url: "https://play.google.com/store/apps/details?id=cris.org.in.prs.ima",
      entity: "IRCTC Rail Connect",
      likes: 67
    },
    ev_tr04: {
      id: "ev_tr04",
      source: "reddit",
      text: "Indian travel OTAs have the worst dark patterns. You have to uncheck 4 different add-ons like baggage tags and medical protection just to book a one hour flight.",
      title: "Why is booking domestic flights in India such an ordeal?",
      author: null,
      rating: null,
      date: null,
      url: "https://reddit.com/r/india/comments/travel_dark_patterns",
      entity: "Reddit Discussion",
      likes: 0
    },
    ev_tr05: {
      id: "ev_tr05",
      source: "play_store",
      text: "Prediction algorithm showed 85% confirmation chance, but tatkal failed and server showed error code 502 while debiting money.",
      title: null,
      author: "Naveen Raj",
      rating: 1,
      date: "2026-09-29",
      url: "https://play.google.com/store/apps/details?id=com.confirmtkt.lite",
      entity: "ConfirmTkt: Train Ticket Booking",
      likes: 29
    },
    ev_tr06: {
      id: "ev_tr06",
      source: "play_store",
      text: "Airline cancelled Delhi-Mumbai flight due to fog. Yatra credited refund to 'Yatra e-cash' instead of my ICICI account. Why should my money be locked in their wallet?",
      title: null,
      author: "Manish Agarwal",
      rating: 1,
      date: "2026-10-02",
      url: "https://play.google.com/store/apps/details?id=com.yatra.base",
      entity: "Yatra: Flight, Hotel, Train",
      likes: 42
    }
  },
  warnings: []
};

export const EDTECH_REPORT = {
  scan_id: "disc_edtech_india",
  mode: 3,
  query: "EdTech",
  generated_at: new Date().toISOString(),
  keywords: {
    broad: "edtech apps",
    specific: ["best learning app India", "competitive exam test series"],
    category: "EdTech & Education"
  },
  credits: {
    serpapi_live: 4,
    serpapi_cached: 4,
    youcom_live: 2,
    youcom_cached: 1
  },
  verdict: {
    kind: "discovery",
    label: null,
    score: null,
    headline: "Identified 3 systemic cross-competitor gaps across 4 leading learning platforms",
    breakdown: [
      {
        factor: "Cross-App Systemic Gaps",
        score: 28,
        max: 30,
        explanation: "Aggressive sales calls, auto-renew subscription traps, and stale question banks repeat across apps",
        evidence_ids: ["ev_ed01", "ev_ed02"]
      },
      {
        factor: "Incumbent Saturation",
        score: 18,
        max: 20,
        explanation: "Top 4 Indian test-prep platforms evaluated",
        evidence_ids: []
      }
    ]
  },
  trend: {
    keyword: "edtech apps",
    geo: "IN",
    points: [
      { date: "2025-12", value: 50 },
      { date: "2026-01", value: 65 },
      { date: "2026-02", value: 62 },
      { date: "2026-03", value: 70 },
      { date: "2026-04", value: 75 },
      { date: "2026-05", value: 78 },
      { date: "2026-06", value: 80 },
      { date: "2026-07", value: 74 },
      { date: "2026-08", value: 76 },
      { date: "2026-09", value: 82 },
      { date: "2026-10", value: 85 },
      { date: "2026-11", value: 88 }
    ],
    change_pct: 18.2,
    direction: "rising"
  },
  competitors: [
    {
      name: "Physics Wallah: Live Learning",
      product_id: "xyz.penpencil.physicswala",
      rating: 4.4,
      installs: "10M+",
      icon: "https://play-lh.googleusercontent.com/pw-app",
      url: "https://play.google.com/store/apps/details?id=xyz.penpencil.physicswala",
      source: "play_store",
      reviews_scanned: 100
    },
    {
      name: "Unacademy: Learner App",
      product_id: "unacademy.learner",
      rating: 4.2,
      installs: "50M+",
      icon: "https://play-lh.googleusercontent.com/unacademy-app",
      url: "https://play.google.com/store/apps/details?id=unacademy.learner",
      source: "play_store",
      reviews_scanned: 100
    },
    {
      name: "BYJU'S: The Learning App",
      product_id: "com.byjus.thelearningapp",
      rating: 3.5,
      installs: "100M+",
      icon: "https://play-lh.googleusercontent.com/byjus-app",
      url: "https://play.google.com/store/apps/details?id=com.byjus.thelearningapp",
      source: "play_store",
      reviews_scanned: 100
    }
  ],
  clusters: [
    {
      id: "cl_1",
      group: "pain",
      title: "Relentless Sales Telemarketing After Free Signups",
      summary: "Students and parents report receiving 5 to 10 persistent sales calls per day pressing expensive annual courses right after free registration.",
      severity: "high",
      frequency: {
        count: 49,
        total: 300,
        label: "49 of 300 reviews"
      },
      apps_affected: [
        "Unacademy: Learner App",
        "BYJU'S: The Learning App"
      ],
      evidence_ids: ["ev_ed01"],
      ai_suggested: false
    },
    {
      id: "cl_2",
      group: "pain",
      title: "Video Player Stutter & Live Class Buffer During Peak Hours",
      summary: "Live sessions crash repeatedly at 6 PM batch times with server bandwidth bottlenecks, forcing students to wait for offline recordings.",
      severity: "high",
      frequency: {
        count: 36,
        total: 300,
        label: "36 of 300 reviews"
      },
      apps_affected: [
        "Physics Wallah: Live Learning",
        "Unacademy: Learner App"
      ],
      evidence_ids: ["ev_ed02"],
      ai_suggested: false
    }
  ],
  opportunities: [
    {
      id: "op_1",
      title: "No-Sales-Call Self-Paced Exam Prep",
      pitch: "A distraction-free, zero-spam learning portal where phone numbers are never shared with sales telemarketers.",
      target_user: "Self-driven JEE/NEET and UPSC aspirants in India",
      addresses_cluster_ids: ["cl_1"],
      evidence_ids: ["ev_ed01"],
      ai_suggested: false
    },
    {
      id: "op_2",
      title: "Ultra-Low Bandwidth Adaptive Live Video Engine",
      pitch: "High-concurrency lightweight live classrooms optimized for Tier 2/3 4G networks without buffering.",
      target_user: "Aspirants in smaller towns and coaching hubs",
      addresses_cluster_ids: ["cl_2"],
      evidence_ids: ["ev_ed02"],
      ai_suggested: false
    }
  ],
  news: [],
  evidence: {
    ev_ed01: {
      id: "ev_ed01",
      source: "play_store",
      text: "I signed up to take one free diagnostic test. Since yesterday I have received 7 calls from different sales counselors pushing a ₹45,000 subscription. Unbelievable harassment.",
      title: null,
      author: "Praveen Tiwari",
      rating: 1,
      date: "2026-10-15",
      url: "https://play.google.com/store/apps/details?id=unacademy.learner",
      entity: "Unacademy: Learner App",
      likes: 61
    },
    ev_ed02: {
      id: "ev_ed02",
      source: "play_store",
      text: "Server lags like crazy during 6 PM chemistry live class. App keeps reloading and comments section crashes the video feed.",
      title: null,
      author: "Sourav M.",
      rating: 1,
      date: "2026-10-19",
      url: "https://play.google.com/store/apps/details?id=xyz.penpencil.physicswala",
      entity: "Physics Wallah: Live Learning",
      likes: 44
    }
  },
  warnings: []
};

export const CULTFIT_REPORT = {
  scan_id: "inv_cultfit_india",
  mode: 2,
  query: "Cult.fit",
  generated_at: new Date().toISOString(),
  keywords: {
    broad: "Cult.fit",
    specific: ["Cult.fit reviews", "Cult.fit complaints"],
    category: "Competitor Investigation"
  },
  credits: {
    serpapi_live: 4,
    serpapi_cached: 4,
    youcom_live: 2,
    youcom_cached: 0
  },
  verdict: {
    kind: "trajectory",
    label: "STAGNATING",
    score: 0,
    headline: "Strong group workout community offset by center overbooking and rigid membership pause rules",
    breakdown: [
      {
        factor: "Search Interest Trajectory",
        score: 0,
        max: 1,
        explanation: "Search interest steady (+3.2% vs prior quarter)",
        evidence_ids: []
      },
      {
        factor: "Review Sentiment Drift",
        score: -1,
        max: 1,
        explanation: "Recent reviews (3.42★) drifting below all-time average (4.30★)",
        evidence_ids: ["ev_cf01", "ev_cf02"]
      },
      {
        factor: "Media Sentiment",
        score: 1,
        max: 1,
        explanation: "Expansion into preventive healthcare drives positive press coverage",
        evidence_ids: ["ev_cf04"]
      }
    ]
  },
  trend: {
    keyword: "Cult.fit",
    geo: "IN",
    points: [
      { date: "2025-12", value: 72 },
      { date: "2026-01", value: 95 },
      { date: "2026-02", value: 84 },
      { date: "2026-03", value: 78 },
      { date: "2026-04", value: 75 },
      { date: "2026-05", value: 73 },
      { date: "2026-06", value: 76 },
      { date: "2026-07", value: 72 },
      { date: "2026-08", value: 74 },
      { date: "2026-09", value: 77 },
      { date: "2026-10", value: 75 },
      { date: "2026-11", value: 78 }
    ],
    change_pct: 3.2,
    direction: "flat"
  },
  competitors: [
    {
      name: "cult.fit: Workouts & Fitness",
      product_id: "fit.cure.android",
      rating: 4.3,
      installs: "10M+",
      icon: "https://play-lh.googleusercontent.com/cultfit-app",
      url: "https://play.google.com/store/apps/details?id=fit.cure.android",
      source: "play_store",
      reviews_scanned: 150
    }
  ],
  clusters: [
    {
      id: "cl_1",
      group: "pain",
      title: "Peak Hour Slot Overbooking & Waitlist Dropouts",
      summary: "Users report 7 AM and 7 PM weekday slots vanish within 3 seconds of opening, making it nearly impossible for full-time workers to attend their local center.",
      severity: "high",
      frequency: {
        count: 42,
        total: 100,
        label: "42 of 100 reviews"
      },
      apps_affected: ["cult.fit: Workouts & Fitness"],
      evidence_ids: ["ev_cf01"],
      ai_suggested: false
    },
    {
      id: "cl_2",
      group: "pain",
      title: "Rigid Membership Pause Policies & Hidden Expiry Deductions",
      summary: "Medical pause requests require strict doctor paperwork and travel pauses are capped at 30 days per annual pack, causing members to forfeit paid months.",
      severity: "medium",
      frequency: {
        count: 28,
        total: 100,
        label: "28 of 100 reviews"
      },
      apps_affected: ["cult.fit: Workouts & Fitness"],
      evidence_ids: ["ev_cf02"],
      ai_suggested: false
    },
    {
      id: "cl_3",
      group: "strength",
      title: "High-Energy Trainers & Studio Hygeine",
      summary: "Members consistently praise trainer motivation in S&C and Boxing formats along with clean shower and locker facilities.",
      severity: "low",
      frequency: {
        count: 35,
        total: 50,
        label: "35 of 50 reviews"
      },
      apps_affected: ["cult.fit: Workouts & Fitness"],
      evidence_ids: ["ev_cf03"],
      ai_suggested: false
    }
  ],
  opportunities: [
    {
      id: "op_1",
      title: "Guaranteed-Slot Micro-Boutique Gym Network",
      pitch: "A neighborhood fitness network capping class capacity at 12 participants per coach with guaranteed slot reservations.",
      target_user: "Corporate professionals in metro cities frustrated by 50-person crowded gym classes",
      addresses_cluster_ids: ["cl_1"],
      evidence_ids: ["ev_cf01"],
      ai_suggested: false
    },
    {
      id: "op_2",
      title: "Fair-Pause Flexible Fitness Subscription",
      pitch: "Pay-as-you-go fitness pass with unlimited zero-fee pause days and rolled-over unused monthly credits.",
      target_user: "Frequent business travelers and hybrid workers",
      addresses_cluster_ids: ["cl_2"],
      evidence_ids: ["ev_cf02"],
      ai_suggested: false
    }
  ],
  news: [
    {
      evidence_id: "ev_cf04",
      sentiment: "positive"
    }
  ],
  evidence: {
    ev_cf01: {
      id: "ev_cf01",
      source: "play_store",
      text: "Booking a 7 AM boxing slot at HSR center is harder than booking Tatkal tickets. Slots open at 10 PM and by 10:00:03 everything is full on waitlist. Paying ₹22k for waitlists.",
      title: null,
      author: "Siddharth Rao",
      rating: 1,
      date: "2026-10-14",
      url: "https://play.google.com/store/apps/details?id=fit.cure.android",
      entity: "cult.fit: Workouts & Fitness",
      likes: 49
    },
    ev_cf02: {
      id: "ev_cf02",
      source: "play_store",
      text: "Fractured my ankle and submitted discharge summary. Support said pause is limited to 45 days maximum. My remaining 4 months of membership expired while I was still in recovery.",
      title: null,
      author: "Preeti Verma",
      rating: 1,
      date: "2026-09-28",
      url: "https://play.google.com/store/apps/details?id=fit.cure.android",
      entity: "cult.fit: Workouts & Fitness",
      likes: 37
    },
    ev_cf03: {
      id: "ev_cf03",
      source: "play_store",
      text: "The coaches in Strength & Conditioning are genuinely world-class. Keeps you motivated and the music and vibe is top tier.",
      title: null,
      author: "Vikram Malhotra",
      rating: 5,
      date: "2026-08-20",
      url: "https://play.google.com/store/apps/details?id=fit.cure.android",
      entity: "cult.fit: Workouts & Fitness",
      likes: 18
    },
    ev_cf04: {
      id: "ev_cf04",
      source: "google_news",
      text: "Cult.fit expands into preventive corporate wellness programs across Bangalore, Mumbai, and Delhi-NCR.",
      title: "Fitness aggregators see corporate wellness surge in 2026",
      author: "Economic Times",
      rating: null,
      date: "2026-10-08",
      url: "https://economictimes.indiatimes.com/tech/cultfit-wellness",
      entity: "Google News",
      likes: 0
    }
  },
  warnings: []
};
