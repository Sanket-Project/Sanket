// Geographic choices are reference data, never a source of demand estimates.
// Telangana's complete official list: https://www.telangana.gov.in/about/districts/
// Other states currently contain a partial district reference.
export const INDIA_STATE_DISTRICTS: Record<string, string[]> = {
  "Maharashtra": [
    "Mumbai", "Pune", "Thane", "Nagpur", "Nashik", "Aurangabad", "Solapur",
    "Kolhapur", "Amravati", "Nanded", "Sangli", "Jalgaon", "Akola", "Latur", "Ahmednagar",
  ],
  "Karnataka": [
    "Bengaluru Urban", "Mysuru", "Mangaluru", "Hubballi-Dharwad", "Belagavi",
    "Kalaburagi", "Ballari", "Vijayapura", "Shivamogga", "Tumakuru", "Davanagere",
    "Udupi", "Hassan", "Mandya", "Bengaluru Rural",
  ],
  "Tamil Nadu": [
    "Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem", "Tirunelveli",
    "Tiruppur", "Vellore", "Erode", "Thoothukudi", "Dindigul", "Thanjavur",
    "Kanchipuram", "Cuddalore", "Karur",
  ],
  "Telangana": [
    "Adilabad", "Bhadradri Kothagudem", "Hanumakonda", "Hyderabad", "Jagtial", "Jangaon",
    "Jayashankar Bhupalpally", "Jogulamba Gadwal", "Kamareddy", "Karimnagar", "Khammam",
    "Kumuram Bheem", "Mahabubabad", "Mahabubnagar", "Mancherial", "Medak", "Medchal-Malkajgiri",
    "Mulugu", "Nagarkurnool", "Nalgonda", "Narayanpet", "Nirmal", "Nizamabad", "Peddapalli",
    "Rajanna Sircilla", "Rangareddy", "Sangareddy", "Siddipet", "Suryapet", "Vikarabad",
    "Wanaparthy", "Warangal", "Yadadri Bhuvanagiri",
  ],
  "Delhi": [
    "New Delhi", "Central Delhi", "North Delhi", "South Delhi", "East Delhi",
    "West Delhi", "North East Delhi", "North West Delhi", "South West Delhi",
    "South East Delhi", "Shahdara",
  ],
  "West Bengal": [
    "Kolkata", "Howrah", "North 24 Parganas", "South 24 Parganas", "Hooghly",
    "Nadia", "Murshidabad", "Purba Bardhaman", "Paschim Bardhaman", "Darjeeling",
    "Jalpaiguri", "Malda", "Birbhum", "Bankura", "Purulia",
  ],
  "Gujarat": [
    "Ahmedabad", "Surat", "Vadodara", "Rajkot", "Bhavnagar", "Jamnagar",
    "Junagadh", "Gandhinagar", "Anand", "Kutch", "Mehsana", "Bharuch",
    "Navsari", "Valsad", "Patan",
  ],
  "Uttar Pradesh": [
    "Lucknow", "Kanpur Nagar", "Ghaziabad", "Agra", "Varanasi", "Meerut",
    "Prayagraj", "Bareilly", "Aligarh", "Moradabad", "Saharanpur", "Gorakhpur",
    "Gautam Buddha Nagar", "Firozabad", "Jhansi",
  ],
  "Rajasthan": [
    "Jaipur", "Jodhpur", "Udaipur", "Kota", "Bikaner", "Ajmer", "Bhilwara",
    "Alwar", "Sikar", "Pali", "Sri Ganganagar", "Bharatpur", "Hanumangarh",
    "Chittorgarh", "Tonk",
  ],
  "Bihar": [
    "Patna", "Gaya", "Bhagalpur", "Muzaffarpur", "Darbhanga", "Purnia",
    "Begusarai", "Bhojpur", "Saran", "Katihar", "Munger", "Nalanda",
    "Samastipur", "Sitamarhi", "Vaishali",
  ],
  "Madhya Pradesh": [
    "Bhopal", "Indore", "Jabalpur", "Gwalior", "Ujjain", "Sagar", "Rewa",
    "Satna", "Ratlam", "Dewas", "Khandwa", "Khargone", "Chhindwara",
    "Vidisha", "Hoshangabad",
  ],
  "Kerala": [
    "Thiruvananthapuram", "Ernakulam", "Kozhikode", "Thrissur", "Kollam",
    "Malappuram", "Palakkad", "Kannur", "Alappuzha", "Kottayam", "Pathanamthitta",
    "Idukki", "Wayanad", "Kasaragod",
  ],
  "Andhra Pradesh": [
    "Visakhapatnam", "Krishna", "Guntur", "Nellore", "Kurnool", "Kadapa",
    "Chittoor", "Anantapur", "East Godavari", "Kakinada", "West Godavari",
    "Srikakulam", "Vizianagaram", "Prakasam",
  ],
  "Odisha": [
    "Khordha", "Cuttack", "Sundargarh", "Ganjam", "Sambalpur", "Puri",
    "Balasore", "Bhadrak", "Mayurbhanj", "Angul", "Dhenkanal", "Koraput",
    "Kalahandi", "Bolangir", "Jharsuguda",
  ],
  "Punjab": [
    "Ludhiana", "Amritsar", "Jalandhar", "Patiala", "Bathinda", "Mohali",
    "Hoshiarpur", "Pathankot", "Moga", "Firozpur", "Sangrur", "Barnala",
    "Faridkot", "Kapurthala", "Gurdaspur",
  ],
  "Haryana": [
    "Faridabad", "Gurugram", "Panipat", "Ambala", "Yamunanagar", "Rohtak",
    "Hisar", "Karnal", "Sonipat", "Panchkula", "Bhiwani", "Sirsa",
    "Jhajjar", "Kurukshetra", "Kaithal",
  ],
  "Chhattisgarh": [
    "Raipur", "Durg", "Bilaspur", "Korba", "Raigarh", "Bastar", "Rajnandgaon",
    "Surguja", "Dhamtari", "Mahasamund", "Kanker", "Janjgir-Champa",
    "Kabirdham", "Jashpur", "Balod",
  ],
  "Himachal Pradesh": [
    "Shimla", "Mandi", "Kangra", "Solan", "Una", "Hamirpur", "Bilaspur",
    "Chamba", "Kullu", "Sirmaur", "Kinnaur", "Lahaul and Spiti",
  ],
  "Jharkhand": [
    "Ranchi", "East Singhbhum", "Dhanbad", "Bokaro", "Hazaribagh", "Deoghar",
    "Giridih", "Ramgarh", "Palamu", "Dumka", "West Singhbhum", "Koderma",
    "Chatra", "Garhwa", "Latehar",
  ],
  "Assam": [
    "Kamrup Metropolitan", "Dibrugarh", "Cachar", "Jorhat", "Nagaon",
    "Tinsukia", "Sonitpur", "Barpeta", "Dhubri", "Karimganj", "Golaghat",
    "Sivasagar", "Bongaigaon", "Goalpara", "Lakhimpur",
  ],
  "Uttarakhand": [
    "Dehradun", "Haridwar", "Nainital", "Udham Singh Nagar", "Almora",
    "Pithoragarh", "Pauri Garhwal", "Tehri Garhwal", "Chamoli", "Rudraprayag",
    "Uttarkashi", "Bageshwar", "Champawat",
  ],
  "Goa": ["North Goa", "South Goa"],
  "Jammu and Kashmir": [
    "Srinagar", "Jammu", "Anantnag", "Baramulla", "Udhampur", "Kathua",
    "Pulwama", "Kupwara", "Budgam", "Rajouri",
  ],
};

// Districts that behave like Tier-1 metros (big urban demand, premium mix).
const METRO_KEYWORDS = [
  "mumbai", "pune", "bengaluru urban", "new delhi", "central delhi", "chennai",
  "hyderabad", "kolkata", "ahmedabad", "surat", "thane", "rangereddy",
  "rangareddy", "kamrup metropolitan",
];

// Districts that behave like Tier-2 growth hubs.
const TIER2_KEYWORDS = [
  "nagpur", "nashik", "jaipur", "lucknow", "kanpur", "ghaziabad", "gautam buddha nagar",
  "vadodara", "rajkot", "ludhiana", "amritsar", "patna", "bhopal", "indore",
  "coimbatore", "madurai", "tiruchirappalli", "ernakulam", "kozhikode", "thrissur",
  "thiruvananthapuram", "visakhapatnam", "vijayawada", "krishna", "guntur",
  "bhubaneswar", "khordha", "cuttack", "raipur", "durg", "ranchi", "jamshedpur",
  "east singhbhum", "dehradun", "haridwar", "gurugram", "faridabad", "mysuru",
  "mangaluru", "agra", "varanasi", "meerut", "prayagraj", "jodhpur", "udaipur",
  "warangal", "dibrugarh", "howrah", "jalandhar", "gandhinagar", "mohali", "srinagar", "jammu",
];

/** Classify a district into a demand tier from its name. */
export function districtTier(name: string): "TIER1" | "TIER2" | "TIER3" {
  const n = name.toLowerCase();
  if (METRO_KEYWORDS.some((k) => n.includes(k))) return "TIER1";
  if (TIER2_KEYWORDS.some((k) => n.includes(k))) return "TIER2";
  return "TIER3";
}

/** Stable, fast string hash (FNV-ish) → non-negative int, for deterministic demand. */
export function hashStr(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h | 0);
}

/** All states we can drill into, sorted for the dropdown. */
export const ALL_STATES: string[] = Object.keys(INDIA_STATE_DISTRICTS).sort();
