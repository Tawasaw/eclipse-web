export const donationUrl =
  "https://www.zeffy.com/en-US/donation-form/support-eclipse-30618-build-a-strong-ftc-biobuzz-robot-2";

export const donationEmbedPath = new URL(donationUrl).pathname.replace(
  "/en-US/",
  "/embed/"
);
export const donationEmbedUrl = new URL(donationEmbedPath, donationUrl).href;
