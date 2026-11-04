export interface RatingEvent {
  season: number;
  code: string;
  name: string;
  type: string;
  url: string;
  record?: { wins: number; losses: number; ties: number };
}

export interface TeamRating {
  score: number | null;
  reason: string;
  evidence: RatingEvent | null;
  rookieYear: number | null;
  seasons: number[];
  eventsWithRecords: number;
  bestQualificationRecord: RatingEvent | null;
}
