export default {
  datasource: {
    url: 'file:./prisma/dev.db',
  },
  migrations: {
    seed: 'node scripts/seed.js',
  },
};
